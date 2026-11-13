"""Metadata-only diagnostic retention and task-owned temporary directories."""

import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from amethyst.security.credentials import Redactor


class DiagnosticStore:
    """Only allowlisted operational fields can reach disk; no arbitrary payloads."""

    def __init__(
        self, root: Path, redactor: Redactor, clock: Callable[[], float] = time.time
    ) -> None:
        self.root = root
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.redactor = redactor
        self.clock = clock
        self.expire()

    def record(self, event: str, *, status: str, duration_ms: int = 0) -> str:
        # Enumerations prevent a caller from smuggling prompts or tool bodies.
        if event not in {"task", "model", "tool", "approval", "cleanup"}:
            raise ValueError("Unsupported diagnostic event.")
        if status not in {
            "started",
            "completed",
            "failed",
            "cancelled",
            "denied",
            "timeout",
        }:
            raise ValueError("Unsupported diagnostic status.")
        if duration_ms < 0:
            raise ValueError("Duration cannot be negative.")
        self.expire()
        key = uuid4().hex
        payload = {
            "event": event,
            "status": status,
            "duration_ms": duration_ms,
            "created": self.clock(),
            "saved": False,
        }
        self._write(key, payload)
        return key

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("Invalid log ID.")
        path = self.root / f"{key}.json"
        if path.is_symlink():
            raise ValueError("Log symlinks are not allowed.")
        return path

    def _write(self, key: str, payload: dict[str, object]) -> None:
        path = self._path(key)
        temporary = self.root / f".{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                temporary.chmod(0o600)
                handle.write(self.redactor.redact(json.dumps(payload)))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def save_permanently(self, key: str) -> None:
        self.expire()
        path = self._path(key)
        payload = json.loads(path.read_text())
        payload["saved"] = True
        self._write(key, payload)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list(self) -> tuple[str, ...]:
        self.expire()
        return tuple(
            sorted(p.stem for p in self.root.glob("*.json") if not p.is_symlink())
        )

    def expire(self) -> None:
        cutoff = self.clock() - 7 * 24 * 3600
        for path in self.root.glob("*.json"):
            if path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text())
                if not payload["saved"] and payload["created"] <= cutoff:
                    path.unlink()
            except (ValueError, KeyError, TypeError):
                # Corrupt metadata never gains indefinite retention.
                path.unlink()


class TaskTemporaryData:
    """Owns only directories it creates; never deletes user workspace/source data."""

    def __init__(self, parent: Path | None = None) -> None:
        self.parent = parent
        self._paths: dict[str, Path] = {}

    def create(self, task_id: str) -> Path:
        if task_id not in self._paths:
            self._paths[task_id] = Path(
                tempfile.mkdtemp(prefix="amethyst-task-", dir=self.parent)
            )
        return self._paths[task_id]

    def cleanup(self, task_id: str) -> None:
        path = self._paths.pop(task_id, None)
        if path is not None:
            shutil.rmtree(path)

    def close(self) -> None:
        for task_id in tuple(self._paths):
            self.cleanup(task_id)
