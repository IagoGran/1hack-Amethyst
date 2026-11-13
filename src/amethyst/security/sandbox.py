"""Docker-only, read-only workspace execution with bounded output and cleanup."""

import asyncio
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
    ApprovalStatus,
    ContractError,
    ErrorCode,
    OperationContext,
    ProposedAction,
    SandboxRequest,
    SandboxResult,
)
from amethyst.security.permissions import ApprovalEngine, fingerprint


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool = False


class ContainerTransport(Protocol):
    async def run(
        self, args: tuple[str, ...], timeout: float, output_limit: int
    ) -> ProcessResult:
        """Invoke the configured container client with bounded output.

        Parameters
        ----------
        args : tuple[str, ...]
            Container-client arguments.
        timeout : float
            Maximum duration in seconds.
        output_limit : int
            Combined output byte cap.

        Returns
        -------
        ProcessResult
            Client exit status and captured output.
        """
        ...


class DockerTransport:
    """Only executes the configured Docker client; never accepts a host command."""

    def __init__(self, socket: Path = Path("/var/run/docker.sock")) -> None:
        """Select the Docker executable and an explicit local Unix socket.

        Parameters
        ----------
        socket : Path
            Absolute local daemon socket; remote contexts are not used.

        Returns
        -------
        None
        """
        executable = shutil.which("docker")
        if executable is None:
            raise ContractError(ErrorCode.UNAVAILABLE, "Docker is not installed.")
        if not socket.is_absolute():
            raise ValueError("A local absolute Docker socket path is required.")
        self.executable = executable
        self.socket = socket

    async def run(
        self, args: tuple[str, ...], timeout: float, output_limit: int
    ) -> ProcessResult:
        """Run Docker with a sanitized environment and drain both output streams.

        Parameters
        ----------
        args : tuple[str, ...]
            Docker arguments, never a host shell command.
        timeout : float
            Maximum client duration in seconds.
        output_limit : int
            Combined stdout/stderr byte cap.

        Returns
        -------
        ProcessResult
            Status and bounded UTF-8 output; invalid byte sequences are omitted.
        """
        process = await asyncio.create_subprocess_exec(
            self.executable,
            "--host",
            f"unix://{self.socket}",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Do not inherit arbitrary Docker contexts/remote hosts or user secrets.
            env={"PATH": os.defpath, "HOME": "/nonexistent", "LANG": "C.UTF-8"},
        )
        captured: list[bytearray] = [bytearray(), bytearray()]
        total = 0
        truncated = False

        async def drain(stream: asyncio.StreamReader | None, target: bytearray) -> None:
            """Drain a pipe while sharing the combined byte budget.

            Parameters
            ----------
            stream : asyncio.StreamReader or None
                Subprocess pipe.
            target : bytearray
                Destination for retained bytes.

            Returns
            -------
            None
            """
            nonlocal total, truncated
            assert stream is not None
            while chunk := await stream.read(8192):
                available = max(0, output_limit - total)
                target.extend(chunk[:available])
                total += min(len(chunk), available)
                truncated |= len(chunk) > available

        readers = [
            asyncio.create_task(drain(process.stdout, captured[0])),
            asyncio.create_task(drain(process.stderr, captured[1])),
        ]
        try:
            async with asyncio.timeout(timeout):
                await process.wait()
                await asyncio.gather(*readers)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            raise
        return ProcessResult(
            process.returncode or 0,
            captured[0].decode(errors="ignore"),
            captured[1].decode(errors="ignore"),
            truncated,
        )


class DockerSandbox:
    """Mounts only the approved workspace, read-only; no command may edit files.

    A pinned, pre-provisioned image is required. No image pulls, host fallback,
    arbitrary mounts, Docker socket mounts, privileged mode, or shell interpolation.
    Runtime/kernel/daemon and the configured image remain trusted.
    """

    def __init__(
        self,
        workspace: Path,
        image: str,
        approvals: ApprovalEngine,
        transport: ContainerTransport,
        *,
        enabled: bool = False,
        limits: Limits | None = None,
    ) -> None:
        """Configure a disabled-by-default sandbox for one approved workspace.

        Parameters
        ----------
        workspace : Path
            Existing workspace directory.
        image : str
            Trusted pre-provisioned image pinned by digest.
        approvals : ApprovalEngine
            Shared user-approval service.
        transport : ContainerTransport
            Local Docker client or deterministic test double.
        enabled : bool
            Trusted bootstrap switch, set only after host validation.
        limits : Limits or None
            Configured command/output ceilings.

        Returns
        -------
        None
        """
        self.workspace = workspace.resolve(strict=True)
        self.image = image
        self.approvals = approvals
        self.transport = transport
        self.enabled = enabled
        self.limits = limits or Limits()
        if not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9._/:_-]*@sha256:[0-9a-f]{64}", image
        ):
            raise ValueError("A trusted image pinned by SHA-256 digest is required.")
        if any(c in str(self.workspace) for c in ",\n\r\x00"):
            raise ValueError("Workspace path cannot be represented safely as a mount.")

    def _validate(self, request: SandboxRequest) -> None:
        """Reject commands outside the configured workspace or resource limits.

        Parameters
        ----------
        request : SandboxRequest
            Proposed command.

        Returns
        -------
        None
        """
        relative = PurePosixPath(request.working_directory)
        if (
            request.workspace != self.workspace
            or not request.workspace.is_dir()
            or request.workspace.is_symlink()
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in request.working_directory
            or not request.argv
            or not request.argv[0]
            or any("\x00" in arg for arg in request.argv)
            or not (0 < request.timeout_seconds <= self.limits.command_seconds)
            or not (0 < request.output_limit_bytes <= self.limits.output_bytes)
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Invalid sandbox workspace, command, or limits.",
            )
        location = self.workspace
        for part in relative.parts:
            location = location / part
            if location.is_symlink():
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED,
                    "Sandbox working directory cannot be a symlink.",
                )
        if not location.is_dir():
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Sandbox working directory does not exist."
            )

    def proposal(self, request: SandboxRequest) -> ProposedAction:
        """Bind command, image, network scope, and limits to an approval fingerprint.

        Parameters
        ----------
        request : SandboxRequest
            Command to present for explicit review.

        Returns
        -------
        ProposedAction
            Exact action required before execution.
        """
        self._validate(request)
        scope = (
            str(self.workspace),
            f"network:{'bridge' if request.network_enabled else 'none'}",
        )
        payload = asdict(request)
        payload.pop("approval_id")
        payload.pop("fingerprint")
        payload["workspace"] = str(self.workspace)
        payload["image"] = self.image
        payload["workspace_mode"] = "read_only"
        return ProposedAction(
            request.action_id,
            "sandbox.run",
            f"Run {request.argv!r} in a container with a read-only workspace",
            scope,
            fingerprint(payload),
            high_impact=request.network_enabled,
        )

    def _create_args(self, request: SandboxRequest, name: str) -> tuple[str, ...]:
        """Build the fixed container profile without invoking a host shell.

        Parameters
        ----------
        request : SandboxRequest
            Validated command and resource limits.
        name : str
            Unique name used for lifecycle management.

        Returns
        -------
        tuple[str, ...]
            Docker create arguments.
        """
        return (
            "create",
            "--name",
            name,
            "--pull",
            "never",
            "--runtime",
            "runc",
            "--ipc",
            "private",
            "--cgroupns",
            "private",
            "--no-healthcheck",
            "--log-driver",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--network",
            "bridge" if request.network_enabled else "none",
            "--mount",
            f"type=bind,src={self.workspace},dst=/workspace,readonly,bind-recursive=disabled",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--workdir",
            str(PurePosixPath("/workspace") / request.working_directory),
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint",
            request.argv[0],
            self.image,
            *request.argv[1:],
        )

    async def _check_image(self) -> None:
        """Reject image volumes that would bypass workspace and retention policy.

        Parameters
        ----------
        None

        Returns
        -------
        None

        Notes
        -----
        Only local image metadata is read; missing images are never pulled.
        The pinned image and the local daemon remain trusted components.
        """
        result = await self.transport.run(
            ("image", "inspect", "--format", "{{json .Config.Volumes}}", self.image),
            10,
            4096,
        )
        if (
            result.returncode
            or result.truncated
            or result.stdout.strip()
            not in {
                "null",
                "{}",
            }
        ):
            raise ContractError(
                ErrorCode.UNAVAILABLE,
                "A local image without declared volumes is required.",
            )

    async def _execute(
        self, request: SandboxRequest, name: str, limit: int
    ) -> SandboxResult:
        """Create, attach, and confirm a terminal container state exactly once.

        Parameters
        ----------
        request : SandboxRequest
            Authorized command.
        name : str
            Container lifecycle identifier.
        limit : int
            Combined output byte limit.

        Returns
        -------
        SandboxResult
            Confirmed command result.
        """
        created = await self.transport.run(self._create_args(request, name), 15, 4096)
        if created.returncode:
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Container could not be created."
            )
        output = await self.transport.run(
            ("start", "--attach", name), request.timeout_seconds, limit
        )
        status = await self.transport.run(
            ("inspect", "--format", "{{json .State}}", name), 10, 4096
        )
        try:
            state = json.loads(status.stdout)
            if (
                status.returncode
                or status.truncated
                or not isinstance(state, dict)
                or state.get("Status") != "exited"
                or state.get("Running") is not False
                or state.get("Error") != ""
                or type(state.get("ExitCode")) is not int
                or not 0 <= state["ExitCode"] <= 255
                or (output.returncode and output.returncode != state["ExitCode"])
            ):
                raise ValueError
        except (ValueError, TypeError):
            raise ContractError(
                ErrorCode.OUTCOME_UNKNOWN, "Container outcome could not be confirmed."
            ) from None
        return SandboxResult(
            state["ExitCode"], output.stdout, output.stderr, truncated=output.truncated
        )

    async def _remove(self, name: str) -> None:
        """Finish bounded container cleanup even after repeated cancellation.

        Parameters
        ----------
        name : str
            Container to stop and remove.

        Returns
        -------
        None

        Notes
        -----
        Unconfirmed cleanup is an uncertain outcome, never a successful command.
        """
        cleanup = asyncio.create_task(
            self.transport.run(("rm", "--force", "--volumes", name), 15, 4096)
        )
        cancelled = False
        try:
            while True:
                try:
                    removed = await asyncio.shield(cleanup)
                    break
                except asyncio.CancelledError:
                    if cleanup.cancelled():
                        raise RuntimeError("Cleanup was cancelled.") from None
                    cancelled = True
            if removed.returncode:
                raise RuntimeError("Cleanup failed.")
        except Exception:
            raise ContractError(
                ErrorCode.OUTCOME_UNKNOWN, "Container cleanup could not be confirmed."
            ) from None
        if cancelled:
            raise asyncio.CancelledError

    async def run(
        self, request: SandboxRequest, context: OperationContext
    ) -> SandboxResult:
        """Execute one approved command within the validated container profile.

        Parameters
        ----------
        request : SandboxRequest
            Exact command and reviewed approval reference.
        context : OperationContext
            Active task, session, and remaining limits.

        Returns
        -------
        SandboxResult
            Confirmed exit status or timeout after cleanup.

        Notes
        -----
        The caller enables this adapter only after host acceptance. Cancellation
        waits for cleanup; commands and uncertain outcomes are never retried.
        """
        if not self.enabled:
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Sandbox is disabled pending runtime validation."
            )
        proposal = self.proposal(request)
        reviewed = await self.approvals.inspect(request.approval_id)
        if (
            proposal.fingerprint != request.fingerprint
            or proposal not in reviewed.request.actions
            or reviewed.status != ApprovalStatus.GRANTED
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Sandbox proposal changed."
            )
        name = f"amethyst-{uuid4().hex}"
        limit = min(request.output_limit_bytes, context.output_limit_bytes)
        result: SandboxResult
        create_attempted = False
        try:
            # Whole create/start/inspect phase shares the command deadline.
            async with asyncio.timeout(
                min(request.timeout_seconds, context.timeout_seconds)
            ):
                await self._check_image()
                # Image inspection can yield; recheck revocation immediately
                # before the first container mutation, then consume exactly once.
                await self.approvals.consume(
                    request.approval_id,
                    request.action_id,
                    proposal.fingerprint,
                    context,
                )
                create_attempted = True
                result = await self._execute(request, name, limit)
        except TimeoutError:
            result = SandboxResult(None, outcome="timeout")
        finally:
            if create_attempted:
                await self._remove(name)
        return result
