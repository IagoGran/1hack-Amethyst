"""Best-effort local CPU, memory, and GPU telemetry for the desktop panel."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """One sample of machine-wide resource use and optional GPU telemetry.

    Parameters
    ----------
    cpu_percent, memory_percent, gpu_percent, gpu_memory_percent : float or None
        Percentages reported by the available local telemetry sources.
    ollama_models : tuple of str
        Names of models currently loaded in the local Ollama daemon.
    ollama_vram_bytes : int or None
        VRAM allocated by loaded Ollama models, when reported by Ollama.
    """

    cpu_percent: float | None
    memory_percent: float | None
    gpu_percent: float | None
    gpu_memory_percent: float | None
    ollama_models: tuple[str, ...] = ()
    ollama_vram_bytes: int | None = None


class ResourceMonitor:
    """Sample Linux procfs and NVIDIA telemetry without changing device state."""

    def __init__(self) -> None:
        """Prepare CPU counter state for calculating usage between samples.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._last_cpu: tuple[int, int] | None = None

    def sample(self, ollama_endpoint: str | None = None) -> ResourceSnapshot:
        """Collect one best-effort snapshot without inventing unavailable values.

        Parameters
        ----------
        ollama_endpoint : str or None
            Configured local Ollama endpoint, if one exists.

        Returns
        -------
        ResourceSnapshot
            Machine-wide percentages; unsupported measurements are ``None``.
        """
        model_names, vram_bytes = self._ollama_usage(ollama_endpoint)
        return ResourceSnapshot(
            self._cpu_percent(),
            self._memory_percent(),
            *self._gpu_percentages(),
            model_names,
            vram_bytes,
        )

    @staticmethod
    def _ollama_usage(endpoint: str | None) -> tuple[tuple[str, ...], int | None]:
        """Read loaded model names and reported VRAM from a local Ollama API.

        Parameters
        ----------
        endpoint : str or None
            Configured Ollama base URL.

        Returns
        -------
        tuple
            Loaded model names and VRAM bytes, or empty values when unavailable.
        """
        base = endpoint or "http://localhost:11434"
        parsed = urlsplit(base)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        ):
            return (), None
        try:
            with urlopen(base.rstrip("/") + "/api/ps", timeout=0.5) as response:
                payload = json.loads(response.read(1_000_000))
            models = payload.get("models", [])
            if not isinstance(models, list):
                return (), None
            names = tuple(
                str(model.get("name", "unknown"))
                for model in models
                if isinstance(model, dict)
            )
            sizes = [
                model.get("size_vram")
                for model in models
                if isinstance(model, dict) and isinstance(model.get("size_vram"), int)
            ]
            return names, sum(sizes) if sizes else None
        except (OSError, ValueError, TypeError, AttributeError):
            return (), None

    def _cpu_percent(self) -> float | None:
        """Calculate CPU busy percentage from consecutive Linux procfs samples.

        Returns
        -------
        float or None
            Busy percentage, or ``None`` when procfs is unavailable.
        """
        try:
            values = [
                int(value)
                for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]
            ]
        except (OSError, ValueError, IndexError):
            return None
        if len(values) < 4:
            return None
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total, idle_total = sum(values), idle
        previous = self._last_cpu
        self._last_cpu = (total, idle_total)
        if previous is None or total <= previous[0]:
            return None
        elapsed = total - previous[0]
        idle_delta = idle_total - previous[1]
        return max(0.0, min(100.0, (1 - idle_delta / elapsed) * 100))

    @staticmethod
    def _memory_percent() -> float | None:
        """Read total and available physical memory from Linux procfs.

        Returns
        -------
        float or None
            Used memory percentage, or ``None`` when unavailable.
        """
        try:
            values = {}
            with open("/proc/meminfo", encoding="ascii") as stream:
                for line in stream:
                    key, raw = line.split(":", 1)
                    values[key] = int(raw.strip().split()[0])
            total = values["MemTotal"]
            available = values.get("MemAvailable")
            if not available or total <= 0:
                return None
            return (total - available) / total * 100
        except (OSError, KeyError, ValueError):
            return None

    @staticmethod
    def _gpu_percentages() -> tuple[float | None, float | None]:
        """Query NVIDIA utilization when its read-only CLI is installed.

        Returns
        -------
        tuple
            GPU utilization and memory percentages, or ``None`` values.
        """
        executable = shutil.which("nvidia-smi")
        if executable is None:
            return None, None
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            gpu, used, total = (
                float(value.strip())
                for value in result.stdout.splitlines()[0].split(",")
            )
            return gpu, (used / total * 100) if total > 0 else None
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return None, None
