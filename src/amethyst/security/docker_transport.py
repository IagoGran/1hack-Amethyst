"""Bounded local Docker client transport with a sanitized environment."""

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from amethyst.domain.contracts import ContractError, ErrorCode


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
