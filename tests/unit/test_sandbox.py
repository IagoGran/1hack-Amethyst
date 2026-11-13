import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from amethyst.domain.contracts import (
    ApprovalRequest,
    ContractError,
    ErrorCode,
    OperationContext,
    SandboxRequest,
)
from amethyst.security.permissions import ApprovalEngine
from amethyst.security.sandbox import DockerSandbox, ProcessResult

IMAGE = "example.invalid/amethyst@sha256:" + "a" * 64
CTX = OperationContext("task", "session", timeout_seconds=1)


class Transport:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.calls: list[tuple[str, ...]] = []
        self.started = asyncio.Event()

    async def run(
        self, args: tuple[str, ...], timeout: float, output_limit: int
    ) -> ProcessResult:
        self.calls.append(args)
        if args[0] == "create":
            return ProcessResult(1 if self.mode == "create_failure" else 0, "id", "")
        if args[0] == "start":
            self.started.set()
            if self.mode in {"wait", "timeout"}:
                await asyncio.sleep(20)
            return ProcessResult(0, "bounded output", "", self.mode == "truncated")
        if args[0] == "inspect":
            return ProcessResult(
                1 if self.mode == "inspect_failure" else 0,
                "invalid" if self.mode == "invalid_status" else "7",
                "",
            )
        return ProcessResult(1 if self.mode == "cleanup_failure" else 0, "", "")


async def configured(
    root: Path, mode: str = "success"
) -> tuple[DockerSandbox, SandboxRequest, Transport]:
    engine = ApprovalEngine("session")
    engine.open_task("task")
    transport = Transport(mode)
    sandbox = DockerSandbox(root, IMAGE, engine, transport, enabled=True)
    request = SandboxRequest(
        "action",
        "approval",
        "",
        root,
        ("python", "-V"),
        timeout_seconds=0.02 if mode == "timeout" else 1,
    )
    action = sandbox.proposal(request)
    await engine.request(ApprovalRequest("approval", "task", "session", (action,)))
    await engine.decide("approval", granted=True)
    return sandbox, replace(request, fingerprint=action.fingerprint), transport


@pytest.mark.parametrize("mode", ["success", "truncated"])
def test_sandbox_policy_output_and_exit_code(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        sandbox, request, transport = await configured(tmp_path, mode)
        result = await sandbox.run(request, CTX)
        assert result.exit_code == 7
        assert result.truncated == (mode == "truncated")
        args = transport.calls[0]
        assert args[args.index("--network") + 1] == "none"
        assert "--read-only" in args
        assert args[args.index("--cap-drop") + 1] == "ALL"
        assert args[args.index("--security-opt") + 1] == "no-new-privileges"
        assert "readonly,bind-recursive=disabled" in args[args.index("--mount") + 1]
        assert args.count("--mount") == 1
        assert transport.calls[-1][0] == "rm"
        with pytest.raises(ContractError):
            await sandbox.run(request, CTX)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode", ["create_failure", "inspect_failure", "invalid_status", "cleanup_failure"]
)
def test_sandbox_uncertain_failures_do_not_retry(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        sandbox, request, transport = await configured(tmp_path, mode)
        with pytest.raises(ContractError):
            await sandbox.run(request, CTX)
        assert sum(args[0] == "create" for args in transport.calls) == 1
        assert transport.calls[-1][0] == "rm"

    asyncio.run(scenario())


def test_sandbox_timeout_and_cancellation_stop_container(tmp_path: Path) -> None:
    async def scenario() -> None:
        sandbox, request, transport = await configured(tmp_path, "timeout")
        assert (await sandbox.run(request, CTX)).outcome == "timeout"
        assert transport.calls[-1][0] == "rm"
        sandbox, request, transport = await configured(tmp_path, "wait")
        worker = asyncio.create_task(sandbox.run(request, CTX))
        await transport.started.wait()
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert transport.calls[-1][0] == "rm"

    asyncio.run(scenario())


def test_sandbox_scope_changes_and_disabled_runtime(tmp_path: Path) -> None:
    async def scenario() -> None:
        sandbox, request, transport = await configured(tmp_path)
        for changed in [
            replace(request, argv=("different",)),
            replace(request, network_enabled=True),
        ]:
            with pytest.raises(ContractError):
                await sandbox.run(changed, CTX)
        assert transport.calls == []
        sandbox.enabled = False
        with pytest.raises(ContractError) as error:
            await sandbox.run(request, CTX)
        assert error.value.code == ErrorCode.UNAVAILABLE
        for invalid in [
            replace(request, workspace=tmp_path.parent),
            replace(request, argv=()),
            replace(request, argv=("bad\x00",)),
            replace(request, working_directory="../outside"),
            replace(request, working_directory="missing"),
            replace(request, timeout_seconds=-1),
        ]:
            with pytest.raises(ContractError):
                sandbox.proposal(invalid)
        (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ContractError):
            sandbox.proposal(replace(request, working_directory="link"))
        with pytest.raises(ValueError):
            DockerSandbox(tmp_path, "unpinned:latest", sandbox.approvals, transport)

    asyncio.run(scenario())
