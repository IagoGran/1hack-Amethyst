"""Docker-only, read-only workspace execution with bounded output and cleanup."""

import asyncio
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
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
    ) -> ProcessResult: ...


class DockerTransport:
    """Only executes the configured Docker client; never accepts a host command."""

    def __init__(self, socket: Path = Path("/var/run/docker.sock")) -> None:
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
            captured[0].decode(errors="replace"),
            captured[1].decode(errors="replace"),
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
        return (
            "create",
            "--name",
            name,
            "--pull",
            "never",
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

    async def run(
        self, request: SandboxRequest, context: OperationContext
    ) -> SandboxResult:
        if not self.enabled:
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Sandbox is disabled pending runtime validation."
            )
        proposal = self.proposal(request)
        reviewed = await self.approvals.inspect(request.approval_id)
        if (
            proposal.fingerprint != request.fingerprint
            or proposal not in reviewed.request.actions
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Sandbox proposal changed."
            )
        await self.approvals.consume(
            request.approval_id,
            request.action_id,
            proposal.fingerprint,
            context,
        )
        name = f"amethyst-{uuid4().hex}"
        limit = min(request.output_limit_bytes, context.output_limit_bytes)
        result: SandboxResult
        try:
            # Whole create/start/inspect phase shares the command deadline.
            async with asyncio.timeout(
                min(request.timeout_seconds, context.timeout_seconds)
            ):
                created = await self.transport.run(
                    self._create_args(request, name), 15, 4096
                )
                if created.returncode:
                    raise ContractError(
                        ErrorCode.UNAVAILABLE, "Container could not be created."
                    )
                output = await self.transport.run(
                    ("start", "--attach", name), request.timeout_seconds, limit
                )
                status = await self.transport.run(
                    ("inspect", "--format", "{{.State.ExitCode}}", name), 10, 128
                )
                if status.returncode:
                    raise ContractError(
                        ErrorCode.OUTCOME_UNKNOWN,
                        "Container outcome could not be confirmed.",
                    )
                try:
                    code = int(status.stdout.strip())
                except ValueError:
                    raise ContractError(
                        ErrorCode.OUTCOME_UNKNOWN, "Invalid container exit status."
                    ) from None
                result = SandboxResult(
                    code, output.stdout, output.stderr, truncated=output.truncated
                )
        except TimeoutError:
            result = SandboxResult(None, outcome="timeout")
        finally:
            # rm -f stops the container, even when its client was interrupted.
            # Shield cleanup so one cancellation cannot leave it running.
            cleanup = asyncio.create_task(
                self.transport.run(("rm", "--force", name), 15, 4096)
            )
            try:
                removed = await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                removed = await cleanup
                if removed.returncode:
                    raise ContractError(
                        ErrorCode.OUTCOME_UNKNOWN,
                        "Container cleanup could not be confirmed.",
                    ) from None
                raise
            except Exception:
                raise ContractError(
                    ErrorCode.OUTCOME_UNKNOWN,
                    "Container cleanup could not be confirmed.",
                ) from None
            if removed.returncode:
                raise ContractError(
                    ErrorCode.OUTCOME_UNKNOWN,
                    "Container cleanup could not be confirmed.",
                )
        return result
