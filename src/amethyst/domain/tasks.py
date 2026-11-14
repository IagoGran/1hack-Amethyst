"""Basic types for representing agent task state."""

from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    """Visible states for a task lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED_FOR_BUDGET = "paused_for_budget"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Task:
    """Minimal representation of a work request."""

    id: str
    request: str
    status: TaskStatus = TaskStatus.PENDING
    conversation_id: str = ""


TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
    }
)
TASK_STATUS_LABELS = {
    TaskStatus.PENDING: "Pending",
    TaskStatus.RUNNING: "Running",
    TaskStatus.AWAITING_APPROVAL: "Awaiting approval",
    TaskStatus.PAUSED_FOR_BUDGET: "Paused for budget",
    TaskStatus.COMPLETED: "Completed",
    TaskStatus.CANCELLED: "Cancelled",
    TaskStatus.FAILED: "Failed",
}
