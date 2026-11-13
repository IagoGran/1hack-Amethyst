"""Desktop boundary; asynchronous calls must not block the GUI event thread."""

from collections.abc import AsyncIterator
from typing import Protocol

from amethyst.domain.contracts import StartTask, TaskEvent
from amethyst.domain.tasks import Task


class ApplicationService(Protocol):
    async def start_task(self, request: StartTask) -> Task:
        """Return a task promptly; resume a conversation using its existing ID."""
        ...

    async def get_task(self, task_id: str) -> Task: ...

    def events(self, task_id: str, after_sequence: int = 0) -> AsyncIterator[TaskEvent]:
        """Replay then follow ordered events; close after terminal state delivery."""
        ...

    async def cancel_task(self, task_id: str) -> Task:
        """Return acknowledged state; no further tool calls after cancellation."""
        ...

    async def increase_budget(self, task_id: str, additional_tokens: int) -> Task:
        """Only an explicit user request may increase a paused task's budget."""
        ...
