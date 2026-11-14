"""Metadata-only diagnostic retention and task-owned temporary directories."""

import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from amethyst.security.redaction import Redactor


class DiagnosticStore:
    """Only allowlisted operational fields can reach disk; no arbitrary payloads."""

    def __init__(
        self, root: Path, redactor: Redactor, clock: Callable[[], float] = time.time
    ) -> None:
        """Open the application-owned metadata store and expire old records.

        Parameters
        ----------
        root : Path
            Application-owned data directory or approved workspace root.
        redactor : Redactor
            Credential filter shared by the session.
        clock : Callable[[], float]
            Clock used to measure time or evaluate retention.

        Returns
        -------
        None
        """
        self.root = root
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.redactor = redactor
        self.clock = clock
        self.expire()

    def record(self, event: str, *, status: str, duration_ms: int = 0) -> str:
        # Enumerations prevent a caller from smuggling prompts or tool bodies.
        """Persist allowlisted diagnostic metadata without user-content bodies.

        Parameters
        ----------
        event : str
            Typed event delivered to the operation.
        status : str
            Visible task or diagnostic status.
        duration_ms : int
            Nonnegative operation duration in milliseconds.

        Returns
        -------
        str
            Text produced by the operation.
        """
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
        """Resolve an owned log identifier while rejecting invalid IDs and links.

        Parameters
        ----------
        key : str
            Setting, record, or fixture key.

        Returns
        -------
        Path
            Value produced by the operation.
        """
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("Invalid log ID.")
        path = self.root / f"{key}.json"
        if path.is_symlink():
            raise ValueError("Log symlinks are not allowed.")
        return path

    def _write(self, key: str, payload: dict[str, object]) -> None:
        """Atomically replace one redacted metadata record.

        Parameters
        ----------
        key : str
            Setting, record, or fixture key.
        payload : dict[str, object]
            Operation-specific data; never log it wholesale.

        Returns
        -------
        None
        """
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
        """Mark an unexpired diagnostic record for explicit permanent retention.

        Parameters
        ----------
        key : str
            Setting, record, or fixture key.

        Returns
        -------
        None
        """
        self.expire()
        path = self._path(key)
        payload = json.loads(path.read_text())
        payload["saved"] = True
        self._write(key, payload)

    def delete(self, key: str) -> None:
        """Delete the selected owned diagnostic record idempotently.

        Parameters
        ----------
        key : str
            Setting, record, or fixture key.

        Returns
        -------
        None
        """
        self._path(key).unlink(missing_ok=True)

    def list(self) -> tuple[str, ...]:
        """List unexpired diagnostic identifiers in deterministic order.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[str, ...]
            Value produced by the operation.
        """
        self.expire()
        return tuple(
            sorted(p.stem for p in self.root.glob("*.json") if not p.is_symlink())
        )

    def expire(self) -> None:
        """Remove expired unsaved records and corrupt metadata files.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
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
        """Track only temporary directories created by this owner.

        Parameters
        ----------
        parent : Path | None
            Owning widget, descriptor, or temporary-data directory.

        Returns
        -------
        None
        """
        self.parent = parent
        self._paths: dict[str, Path] = {}

    def create(self, task_id: str) -> Path:
        """Create or return the disposable directory belonging to this task.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        Path
            Value produced by the operation.
        """
        if task_id not in self._paths:
            self._paths[task_id] = Path(
                tempfile.mkdtemp(prefix="amethyst-task-", dir=self.parent)
            )
        return self._paths[task_id]

    def cleanup(self, task_id: str) -> None:
        """Remove only the temporary directory owned for the selected task.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        None
        """
        path = self._paths.pop(task_id, None)
        if path is not None:
            shutil.rmtree(path)

    def close(self) -> None:
        """Clean up every task directory owned by this session.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for task_id in tuple(self._paths):
            self.cleanup(task_id)
