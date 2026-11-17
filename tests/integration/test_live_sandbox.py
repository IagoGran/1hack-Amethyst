"""Opt-in Docker acceptance probes; no daemon access in the default test run."""

import asyncio
import errno
import json
import os
import platform
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import uuid4

import pytest

from amethyst.domain.contracts import (
    ApprovalRequest,
    ContractError,
    OperationContext,
    SandboxRequest,
    SandboxResult,
)
from amethyst.security.permissions import ApprovalEngine
from amethyst.security.sandbox import DockerSandbox, DockerTransport, ProcessResult

pytestmark = [
    pytest.mark.live_sandbox,
    pytest.mark.skipif(
        os.environ.get("AMETHYST_LIVE_SANDBOX") != "1",
        reason="Set AMETHYST_LIVE_SANDBOX=1 and configure a pinned local image.",
    ),
]


@pytest.fixture(scope="module")
def runtime(
    record_testsuite_property: Callable[[str, object], None],
) -> tuple[Path, str]:
    """Require explicit configuration and record the tested host/profile.

    Parameters
    ----------
    record_testsuite_property : callable
        Pytest JUnit metadata recorder.

    Returns
    -------
    tuple[Path, str]
        Local Docker socket and pre-provisioned image digest.

    Notes
    -----
    Opted-in configuration failures fail tests instead of silently skipping them.
    This fixture does not install Docker, pull images, or change daemon settings.
    """
    image = os.environ.get("AMETHYST_SANDBOX_IMAGE", "")
    if not image:
        pytest.fail("AMETHYST_SANDBOX_IMAGE must name a local image pinned by digest.")
    socket = Path(os.environ.get("AMETHYST_DOCKER_SOCKET", "/var/run/docker.sock"))
    transport = DockerTransport(socket)
    result = asyncio.run(transport.run(("info", "--format", "{{json .}}"), 15, 65536))
    assert result.returncode == 0 and not result.truncated, "Docker daemon unavailable"
    info = json.loads(result.stdout)
    assert info["OSType"] == "linux"
    assert int(info["ServerVersion"].split(".")[0]) >= 25
    assert info["CgroupVersion"] == "2"
    assert "runc" in info["Runtimes"]
    assert "name=seccomp,profile=builtin" in info["SecurityOptions"]
    for name in ("MemoryLimit", "CpuCfsQuota", "PidsLimit"):
        assert info.get(name) is True, f"Runtime lacks enforced {name}"
    record_testsuite_property("sandbox_profile", "docker-runc-readonly-v1")
    record_testsuite_property("image", image)
    record_testsuite_property("host", platform.platform())
    record_testsuite_property("distribution", platform.freedesktop_os_release())
    record_testsuite_property(
        "windows_build", os.environ.get("AMETHYST_WINDOWS_BUILD", "N/A")
    )
    for name in ("ServerVersion", "KernelVersion", "Architecture", "SecurityOptions"):
        record_testsuite_property(name, info[name])
    return socket, image


@dataclass
class RecordingTransport:
    """Delegate to the real Docker CLI and track only test-owned containers."""

    client: DockerTransport
    names: list[str] = field(default_factory=list)
    starting: asyncio.Event = field(default_factory=asyncio.Event)

    async def run(
        self, args: tuple[str, ...], timeout: float, output_limit: int
    ) -> ProcessResult:
        """Execute a Docker operation and record lifecycle synchronization.

        Parameters
        ----------
        args : tuple[str, ...]
            Docker command arguments.
        timeout : float
            Maximum duration.
        output_limit : int
            Combined output cap.

        Returns
        -------
        ProcessResult
            Real Docker result.
        """
        if args[0] == "create":
            self.names.append(args[args.index("--name") + 1])
        if args[0] == "start":
            self.starting.set()
        return await self.client.run(args, timeout, output_limit)

    async def assert_removed(self) -> None:
        """Confirm every test-owned container has been removed from the daemon.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for name in self.names:
            result = await self.client.run(
                ("ps", "--all", "--filter", f"name=^/{name}$", "--format", "{{.ID}}"),
                10,
                4096,
            )
            assert result.returncode == 0 and not result.stdout.strip()


@dataclass
class Harness:
    """Compose the production approval and sandbox components for acceptance."""

    sandbox: DockerSandbox
    transport: RecordingTransport

    async def approve(self, program: str, **limits: int | float) -> SandboxRequest:
        """Review and authorize exactly one Python command in the test workspace.

        Parameters
        ----------
        program : str
            In-container Python probe.
        **limits : int or float
            Optional timeout and output overrides.

        Returns
        -------
        SandboxRequest
            Request bound to its approved fingerprint.
        """
        token = uuid4().hex
        request = SandboxRequest(
            token,
            token,
            "",
            self.sandbox.workspace,
            ("python", "-c", program),
            timeout_seconds=limits.get("timeout", 30),
            output_limit_bytes=int(limits.get("output", 4096)),
        )
        action = self.sandbox.proposal(request)
        await self.sandbox.approvals.request(
            ApprovalRequest(token, "task", "session", (action,))
        )
        await self.sandbox.approvals.decide(token, granted=True)
        return replace(request, fingerprint=action.fingerprint)

    async def execute(self, request: SandboxRequest) -> SandboxResult:
        """Run a request and verify cleanup even on errors.

        Parameters
        ----------
        request : SandboxRequest
            Reviewed probe request.

        Returns
        -------
        SandboxResult
            Production execution result.
        """
        try:
            return await self.sandbox.run(
                request, OperationContext("task", "session", timeout_seconds=60)
            )
        finally:
            await self.transport.assert_removed()


def harness(root: Path, runtime: tuple[Path, str]) -> Harness:
    """Build a sandbox for a temporary workspace after explicit test opt-in.

    Parameters
    ----------
    root : Path
        Test-owned workspace.
    runtime : tuple[Path, str]
        Configured socket and image.

    Returns
    -------
    Harness
        Sandbox with a fresh approval session.
    """
    engine = ApprovalEngine("session")
    engine.open_task("task")
    transport = RecordingTransport(DockerTransport(runtime[0]))
    return Harness(
        DockerSandbox(root, runtime[1], engine, transport, enabled=True), transport
    )


def test_real_filesystem_and_network_boundaries(
    tmp_path: Path, runtime: tuple[Path, str]
) -> None:
    """Attempt workspace writes, path escapes, privileged mounts, and networking.

    Parameters
    ----------
    tmp_path : Path
        Disposable host directory.
    runtime : tuple[Path, str]
        Validated Docker configuration.

    Returns
    -------
    None
    """
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("host-only-marker")
    (root / "source").write_text("original")
    (root / "escape").symlink_to(outside)
    program = f"""
import ctypes, errno, os, pathlib, socket
root = pathlib.Path('/workspace')
assert (root / 'source').read_text() == 'original'
for path in [root / 'source', root / 'new', pathlib.Path('/etc/amethyst-probe')]:
    try:
        path.write_text('unexpected')
    except OSError as error:
        assert error.errno in (errno.EROFS, errno.EACCES, errno.EPERM)
    else:
        raise AssertionError('write escaped read-only policy')
for path in [root / 'escape', pathlib.Path({str(outside)!r}),
             pathlib.Path('/proc/1/root') / {str(outside).lstrip("/")!r}]:
    assert not path.exists(), 'host file exposed'
assert not pathlib.Path('/var/run/docker.sock').exists()
status = pathlib.Path('/proc/self/status').read_text()
assert 'CapEff:\\t0000000000000000' in status
assert 'NoNewPrivs:\\t1' in status and 'Seccomp:\\t2' in status
assert set(os.listdir('/sys/class/net')) == {{'lo'}}
with socket.socket() as connection:
    connection.settimeout(1)
    assert connection.connect_ex(('192.0.2.1', 80)) == {errno.ENETUNREACH}
libc = ctypes.CDLL(None, use_errno=True)
assert libc.mount(b'none', b'/tmp', b'tmpfs', 0, None) == -1
assert ctypes.get_errno() in (errno.EPERM, errno.EACCES)
pathlib.Path('/tmp/scratch').write_text('ephemeral')
print('boundaries verified')
"""

    async def scenario() -> None:
        """Execute the hostile probe with ordinary command approval.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        runner = harness(root, runtime)
        result = await runner.execute(await runner.approve(program))
        assert result.exit_code == 0, result.stderr
        assert result.stdout.strip() == "boundaries verified"
        assert (root / "source").read_text() == "original"
        assert outside.read_text() == "host-only-marker"
        assert not (root / "new").exists()

    asyncio.run(scenario())


def test_real_exit_output_timeout_and_approvals(
    tmp_path: Path, runtime: tuple[Path, str]
) -> None:
    """Check bounded output, failure exits, timeouts, revocation, and scope changes.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.
    runtime : tuple[Path, str]
        Validated Docker configuration.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise real command outcomes and denied reuse.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        runner = harness(tmp_path, runtime)
        request = await runner.approve("import sys; print('failure'); sys.exit(7)")
        result = await runner.execute(request)
        assert result.exit_code == 7 and result.stdout.strip() == "failure"
        with pytest.raises(ContractError):
            await runner.execute(request)
        noisy = await runner.approve(
            "import os; os.write(1, b'x'*8192); os.write(2, b'y'*8192)", output=512
        )
        result = await runner.execute(noisy)
        assert result.exit_code == 0 and result.truncated
        assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 512
        slow = await runner.approve("import time; time.sleep(60)", timeout=2)
        assert (await runner.execute(slow)).outcome == "timeout"
        revoked = await runner.approve("print('must not run')")
        await runner.sandbox.approvals.revoke(revoked.approval_id)
        before = len(runner.transport.names)
        with pytest.raises(ContractError):
            await runner.execute(revoked)
        changed = await runner.approve("print('reviewed')")
        with pytest.raises(ContractError):
            await runner.execute(replace(changed, network_enabled=True))
        assert len(runner.transport.names) == before

    asyncio.run(scenario())


def test_real_cancellation_removes_running_container(
    tmp_path: Path, runtime: tuple[Path, str]
) -> None:
    """Cancel only after the daemon confirms the container is running.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.
    runtime : tuple[Path, str]
        Validated Docker configuration.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Wait for a running process and verify cancellation cleanup.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        runner = harness(tmp_path, runtime)
        request = await runner.approve("import time; time.sleep(60)")
        worker = asyncio.create_task(runner.execute(request))
        try:
            async with asyncio.timeout(15):
                await runner.transport.starting.wait()
                while True:
                    status = await runner.transport.client.run(
                        (
                            "inspect",
                            "--format",
                            "{{.State.Running}}",
                            runner.transport.names[-1],
                        ),
                        5,
                        128,
                    )
                    if status.returncode == 0 and status.stdout.strip() == "true":
                        break
                    if worker.done():
                        pytest.fail("Container stopped before cancellation probe")
                    await asyncio.sleep(0.05)
        finally:
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
        await runner.transport.assert_removed()

    asyncio.run(scenario())
