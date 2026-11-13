"""Verify Docker CLI isolation and stream handling without a Docker daemon."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from amethyst.domain.contracts import ContractError
from amethyst.security.sandbox import DockerTransport


@dataclass
class Process:
    """Model subprocess pipes and termination without starting a host command."""

    stdout: asyncio.StreamReader = field(default_factory=asyncio.StreamReader)
    stderr: asyncio.StreamReader = field(default_factory=asyncio.StreamReader)
    returncode: int | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait(self) -> int:
        """Wait for simulated exit or forced termination.

        Parameters
        ----------
        None

        Returns
        -------
        int
            Simulated process status.
        """
        await self.finished.wait()
        assert self.returncode is not None
        return self.returncode

    def kill(self) -> None:
        """Simulate forced client termination.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.returncode = -9
        self.finished.set()


def test_transport_combines_byte_limits_and_sanitizes_environment() -> None:
    """Bound both streams even for invalid UTF-8 and avoid inherited credentials.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Drain simulated Docker output through the production transport.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        process = Process(returncode=7)
        process.stdout.feed_data(b"\xff" * 10 + b"output" * 100)
        process.stderr.feed_data(b"error" * 100)
        process.stdout.feed_eof()
        process.stderr.feed_eof()
        process.finished.set()
        spawn = AsyncMock(return_value=process)
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", spawn),
        ):
            result = await DockerTransport().run(("start", "--attach", "owned"), 1, 32)
        assert result.returncode == 7 and result.truncated
        assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 32
        assert spawn.call_args.args[:3] == (
            "/usr/bin/docker",
            "--host",
            "unix:///var/run/docker.sock",
        )
        assert set(spawn.call_args.kwargs["env"]) == {"PATH", "HOME", "LANG"}

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_transport_timeout_and_cancellation_stop_client(cancel: bool) -> None:
    """Terminate and reap the CLI when the surrounding operation stops.

    Parameters
    ----------
    cancel : bool
        Exercise cancellation instead of the transport deadline.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Interrupt an unfinished client with open streams.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        process = Process()
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=process)),
        ):
            worker = asyncio.create_task(
                DockerTransport().run(("start", "--attach", "owned"), 0.01, 32)
            )
            await asyncio.sleep(0)
            if cancel:
                worker.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
                await worker
        assert process.returncode == -9

    asyncio.run(scenario())


def test_transport_requires_docker_and_an_absolute_local_socket() -> None:
    """Reject missing runtime clients and remote or ambiguous endpoints.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    with patch("shutil.which", return_value=None), pytest.raises(ContractError):
        DockerTransport()
    with (
        patch("shutil.which", return_value="/usr/bin/docker"),
        pytest.raises(ValueError),
    ):
        DockerTransport(Path("relative.sock"))
