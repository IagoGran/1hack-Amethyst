import asyncio
import os
from dataclasses import replace
from pathlib import Path

import pytest

from amethyst.domain.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    ContractError,
    ErrorCode,
    OperationContext,
    ProposedAction,
)
from amethyst.security.permissions import ApprovalEngine, PermissionService, fingerprint
from amethyst.security.workspace import Workspace

CTX = OperationContext("task", "session")


async def approve(
    engine: ApprovalEngine, actions: tuple[ProposedAction, ...], key: str = "approval"
) -> str:
    await engine.request(ApprovalRequest(key, "task", "session", actions))
    await engine.decide(key, granted=True)
    return key


def setup(root: Path) -> tuple[ApprovalEngine, PermissionService, Workspace]:
    engine = ApprovalEngine("session")
    engine.open_task("task")
    permissions = PermissionService("session")
    permissions.grant("workspace.read", str(root), recursive=True)
    return engine, permissions, Workspace(root, permissions, engine)


def action(key: str) -> ProposedAction:
    return ProposedAction(
        key, "tool", "Run tool", ("resource",), fingerprint({"key": key})
    )


def test_approval_batch_consumption_and_revocation() -> None:
    async def scenario() -> None:
        engine = ApprovalEngine("session")
        engine.open_task("task")
        a, b = action("a"), action("b")
        key = await approve(engine, (a, b))
        await engine.consume(key, "a", a.fingerprint, CTX)
        assert (await engine.inspect(key)).consumed_action_ids == ("a",)
        with pytest.raises(ContractError):
            await engine.consume(key, "a", a.fingerprint, CTX)
        await engine.revoke(key)
        with pytest.raises(ContractError):
            await engine.consume(key, "b", b.fingerprint, CTX)
        assert (await engine.inspect(key)).status == ApprovalStatus.REVOKED

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "pending",
        "denied",
        "changed",
        "other_action",
        "task",
        "session",
        "expired",
        "closed",
        "missing",
    ],
)
def test_approval_scope_failures(mode: str) -> None:
    async def scenario() -> None:
        engine = ApprovalEngine("session")
        engine.open_task("task")
        a = action("a")
        await engine.request(ApprovalRequest("approval", "task", "session", (a,)))
        if mode != "pending":
            await engine.decide("approval", granted=mode != "denied")
        if mode == "expired":
            await engine.expire_task("task")
        if mode == "closed":
            await engine.end_session("session")
        ctx = (
            replace(CTX, task_id="other")
            if mode == "task"
            else replace(CTX, session_id="other")
            if mode == "session"
            else CTX
        )
        with pytest.raises(ContractError) as error:
            await engine.consume(
                "missing" if mode == "missing" else "approval",
                "other" if mode == "other_action" else "a",
                "changed" if mode == "changed" else a.fingerprint,
                ctx,
            )
        assert error.value.code == ErrorCode.PERMISSION_DENIED

    asyncio.run(scenario())


def test_approval_decisions_wait_and_expiry() -> None:
    async def scenario() -> None:
        engine = ApprovalEngine("session")
        engine.open_task("task")
        a = action("a")
        with pytest.raises(ContractError):
            engine.open_task("task")
        with pytest.raises(ContractError):
            await engine.inspect("missing")
        with pytest.raises(ContractError):
            await engine.request(ApprovalRequest("bad", "unknown", "session", (a,)))
        with pytest.raises(ContractError):
            await engine.request(
                ApprovalRequest("bad", "task", "session", (replace(a, fingerprint=""),))
            )
        await engine.request(ApprovalRequest("approval", "task", "session", (a,)))
        waiter = asyncio.create_task(engine.wait("approval"))
        await asyncio.sleep(0)
        with pytest.raises(ContractError):
            await engine.request(ApprovalRequest("approval", "task", "session", (a,)))
        await engine.decide("approval", granted=True)
        assert (await waiter).status == ApprovalStatus.GRANTED
        with pytest.raises(ContractError):
            await engine.decide("approval", granted=False)
        await engine.consume("approval", a.id, a.fingerprint, CTX)
        assert (await engine.inspect("approval")).status == ApprovalStatus.CONSUMED
        await engine.revoke("approval")
        await engine.end_session("unrelated")
        await engine.end_session("session")
        assert engine.inspect_all()[0].status == ApprovalStatus.EXPIRED
        with pytest.raises(ContractError):
            engine.open_task("another")

    asyncio.run(scenario())


def test_read_grants_are_scoped_and_session_limited(tmp_path: Path) -> None:
    permissions = PermissionService("session")
    grant = permissions.grant("read", str(tmp_path), recursive=True)
    permissions.require(CTX, "read", str(tmp_path / "file"))
    assert permissions.inspect() == (grant,)
    for context, tool, resource in [
        (replace(CTX, session_id="other"), "read", str(tmp_path)),
        (CTX, "write", str(tmp_path)),
        (CTX, "read", str(tmp_path.parent)),
    ]:
        with pytest.raises(ContractError):
            permissions.require(context, tool, resource)
    permissions.revoke(grant.id)
    exact = permissions.grant("sql", "connection:one")
    permissions.require(CTX, "sql", exact.resource)
    permissions.close()
    with pytest.raises(ContractError):
        permissions.require(CTX, "sql", exact.resource)
    with pytest.raises(ContractError):
        permissions.grant("read", "x")


def test_workspace_edit_create_delete_and_expired_diff_cleanup(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, permissions, workspace = setup(tmp_path)
        file = tmp_path / "code.py"
        file.write_text("old\n")
        file.chmod(0o755)
        edit = workspace.propose("code.py", "new\n", CTX)
        assert "-old" in edit.action.changes[0].diff
        assert "+new" in edit.action.changes[0].diff
        assert workspace.read("code.py", CTX) == "old\n"
        with pytest.raises(ContractError):
            await workspace.apply(edit, "missing", CTX)
        await approve(engine, (edit.action,))
        await workspace.apply(edit, "approval", CTX)
        assert file.read_text() == "new\n"
        assert file.stat().st_mode & 0o777 == 0o755
        with pytest.raises(ContractError):
            workspace.propose("code.py", "new\n", CTX)
        create = workspace.propose("empty", "", CTX)
        await approve(engine, (create.action,), "create")
        await workspace.apply(create, "create", CTX)
        delete = workspace.propose("empty", None, CTX)
        assert delete.action.high_impact
        await approve(engine, (delete.action,), "delete")
        await workspace.apply(delete, "delete", CTX)
        assert not (tmp_path / "empty").exists()
        await engine.expire_task("task")
        assert not (await engine.inspect("approval")).request.actions[0].changes
        permissions.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["base", "content", "revoked", "created", "symlink"])
def test_workspace_invalidated_proposals_never_write(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        engine, permissions, workspace = setup(tmp_path)
        file = tmp_path / "file"
        if mode != "created":
            file.write_text("before")
        edit = workspace.propose("file", "after", CTX)
        await approve(engine, (edit.action,))
        if mode == "base":
            file.write_text("external change")
        if mode == "content":
            edit = replace(edit, content="unreviewed")
        if mode == "revoked":
            permissions.revoke(permissions.inspect()[0].id)
        if mode == "created":
            file.write_text("someone created this")
        if mode == "symlink":
            file.unlink()
            file.symlink_to(tmp_path / "outside")
        with pytest.raises(ContractError):
            await workspace.apply(edit, "approval", CTX)
        if not file.is_symlink():
            assert file.read_text() != "after"

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "path",
    ["../escape", "/etc/passwd", ".git/config", "a/../../b", "", "a\\b", "a\x00b"],
)
def test_workspace_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    _, _, workspace = setup(tmp_path)
    with pytest.raises(ContractError):
        workspace.read(path, CTX)


def test_workspace_symlinks_special_files_size_encoding_and_missing(
    tmp_path: Path,
) -> None:
    _, _, workspace = setup(tmp_path)
    with pytest.raises(ContractError):
        workspace.read("missing", CTX)
    with pytest.raises(ContractError):
        workspace.propose("missing", None, CTX)
    (tmp_path / "bad").write_bytes(b"\xff")
    with pytest.raises(ContractError):
        workspace.read("bad", CTX)
    with pytest.raises(ContractError):
        workspace.propose("bad", "text", CTX)
    (tmp_path / "dir").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "dir", target_is_directory=True)
    with pytest.raises(ContractError):
        workspace.read("link/file", CTX)
    os.mkfifo(tmp_path / "fifo")
    with pytest.raises(ContractError):
        workspace.read("fifo", CTX)
    (tmp_path / "file").write_text("x")
    os.link(tmp_path / "file", tmp_path / "hardlink")
    with pytest.raises(ContractError):
        workspace.read("file", CTX)
    workspace.max_bytes = 2
    (tmp_path / "large").write_text("too large")
    with pytest.raises(ContractError):
        workspace.read("large", CTX)
    with pytest.raises(ContractError):
        workspace.propose("new", "large", CTX)
