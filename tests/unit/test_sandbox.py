import asyncio
import json
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
        """Initialize deterministic lifecycle synchronization.

        Parameters
        ----------
        mode : str
            Selected result or failure mode.

        Returns
        -------
        None
        """
        self.mode = mode
        self.calls: list[tuple[str, ...]] = []
        self.started = asyncio.Event()
        self.cleaning = asyncio.Event()
        self.release_cleanup = asyncio.Event()
        self.inspecting_image = asyncio.Event()
        self.release_image = asyncio.Event()

    async def run(
        self, args: tuple[str, ...], timeout: float, output_limit: int
    ) -> ProcessResult:
        """Return a deterministic Docker lifecycle response.

        Parameters
        ----------
        args : tuple[str, ...]
            Docker arguments.
        timeout : float
            Requested deadline.
        output_limit : int
            Requested output cap.

        Returns
        -------
        ProcessResult
            Fixture result for the selected failure mode.
        """
        self.calls.append(args)
        if args[0] == "image":
            self.inspecting_image.set()
            if self.mode == "image_wait":
                await self.release_image.wait()
            if self.mode == "image_missing":
                return ProcessResult(1, "", "missing")
            if self.mode == "image_volume":
                return ProcessResult(0, '{"/data": {}}', "")
            return ProcessResult(0, "null", "")
        if args[0] == "create":
            return ProcessResult(1 if self.mode == "create_failure" else 0, "id", "")
        if args[0] == "start":
            self.started.set()
            if self.mode in {"wait", "timeout"}:
                await asyncio.sleep(20)
            return ProcessResult(0, "bounded output", "", self.mode == "truncated")
        if args[0] == "inspect":
            state = {
                "Status": "running" if self.mode == "still_running" else "exited",
                "Running": self.mode == "still_running",
                "Error": "start failed" if self.mode == "start_failure" else "",
                "ExitCode": True if self.mode == "boolean_exit" else 7,
            }
            return ProcessResult(
                1 if self.mode == "inspect_failure" else 0,
                "invalid" if self.mode == "invalid_status" else json.dumps(state),
                "",
            )
        self.cleaning.set()
        if self.mode == "cleanup_wait":
            await self.release_cleanup.wait()
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
    """Check the enforced profile and consumed approval.

    Parameters
    ----------
    tmp_path : Path
        Isolated workspace.
    mode : str
        Output fixture mode.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Run the approved command.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        sandbox, request, transport = await configured(tmp_path, mode)
        result = await sandbox.run(request, CTX)
        assert result.exit_code == 7
        assert result.truncated == (mode == "truncated")
        args = next(args for args in transport.calls if args[0] == "create")
        assert args[args.index("--network") + 1] == "none"
        assert "--read-only" in args
        assert args[args.index("--cap-drop") + 1] == "ALL"
        assert args[args.index("--security-opt") + 1] == "no-new-privileges"
        assert "readonly,bind-recursive=disabled" in args[args.index("--mount") + 1]
        assert args.count("--mount") == 1
        assert args[args.index("--runtime") + 1] == "runc"
        assert args[args.index("--ipc") + 1] == "private"
        assert args[args.index("--cgroupns") + 1] == "private"
        assert args[args.index("--log-driver") + 1] == "none"
        assert "--no-healthcheck" in args
        assert transport.calls[-1][0] == "rm"
        with pytest.raises(ContractError):
            await sandbox.run(request, CTX)

    asyncio.run(scenario())


def test_repeated_cancellation_waits_for_cleanup(tmp_path: Path) -> None:
    """Prevent repeated cancellation from abandoning a running container cleanup.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Interrupt cleanup twice and require its completion before acknowledgement.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        sandbox, request, transport = await configured(tmp_path, "cleanup_wait")
        worker = asyncio.create_task(sandbox.run(request, CTX))
        await transport.cleaning.wait()
        for _ in range(2):
            worker.cancel()
            await asyncio.sleep(0)
            assert not worker.done()
        transport.release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await worker
        assert sum(args[0] == "rm" for args in transport.calls) == 1

    asyncio.run(scenario())


def test_revocation_during_image_check_prevents_creation(tmp_path: Path) -> None:
    """Recheck approval after asynchronous image validation and before execution.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Revoke a reviewed action while image metadata is being checked.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        sandbox, request, transport = await configured(tmp_path, "image_wait")
        worker = asyncio.create_task(sandbox.run(request, CTX))
        await transport.inspecting_image.wait()
        await sandbox.approvals.revoke(request.approval_id)
        transport.release_image.set()
        with pytest.raises(ContractError) as error:
            await worker
        assert error.value.code == ErrorCode.PERMISSION_DENIED
        assert [args[0] for args in transport.calls] == ["image"]

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["image_missing", "image_volume"])
def test_unusable_image_does_not_create_container(tmp_path: Path, mode: str) -> None:
    """Block implicit image volumes and missing images before container creation.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.
    mode : str
        Invalid image fixture.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Check fail-closed image admission.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        sandbox, request, transport = await configured(tmp_path, mode)
        with pytest.raises(ContractError) as error:
            await sandbox.run(request, CTX)
        assert error.value.code == ErrorCode.UNAVAILABLE
        assert [args[0] for args in transport.calls] == ["image"]

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["still_running", "start_failure", "boolean_exit"])
def test_container_state_must_confirm_completion(tmp_path: Path, mode: str) -> None:
    """Reject false success reports and remove containers with uncertain outcomes.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.
    mode : str
        Unconfirmed exit state.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Verify uncertainty is terminal and cleanup still happens.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        sandbox, request, transport = await configured(tmp_path, mode)
        with pytest.raises(ContractError) as error:
            await sandbox.run(request, CTX)
        assert error.value.code == ErrorCode.OUTCOME_UNKNOWN
        assert sum(args[0] == "create" for args in transport.calls) == 1
        assert transport.calls[-1][:3] == ("rm", "--force", "--volumes")

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
