"""Basic types for representing agent task state."""

from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    """Visible states for a task lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Task:
    """Minimal representation of a work request."""

    id: str
    request: str
    status: TaskStatus = TaskStatus.PENDING
