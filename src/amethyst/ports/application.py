"""Desktop boundary; asynchronous calls must not block the GUI event thread."""

from collections.abc import AsyncIterator
from typing import Protocol

from amethyst.domain.contracts import StartTask, TaskEvent
from amethyst.domain.tasks import Task


class ApplicationService(Protocol):
    async def start_task(self, request: StartTask) -> Task:
        """Return a task promptly; resume a conversation using its existing ID.

        Parameters
        ----------
        request : StartTask
            Typed request describing the operation and its scope.

        Returns
        -------
        Task
            Current immutable task snapshot.
        """
        ...

    async def get_task(self, task_id: str) -> Task:
        """Return the current task snapshot by its stable identifier.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        Task
            Current immutable task snapshot.
        """
        ...

    def events(self, task_id: str, after_sequence: int = 0) -> AsyncIterator[TaskEvent]:
        """Replay then follow ordered events; close after terminal state delivery.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.
        after_sequence : int
            Last event sequence already consumed by the subscriber.

        Returns
        -------
        AsyncIterator[TaskEvent]
            Value produced by the operation.
        """
        ...

    async def cancel_task(self, task_id: str) -> Task:
        """Return acknowledged state; no further tool calls after cancellation.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        Task
            Current immutable task snapshot.
        """
        ...

    async def increase_budget(self, task_id: str, additional_tokens: int) -> Task:
        """Only an explicit user request may increase a paused task's budget.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.
        additional_tokens : int
            Positive token increase explicitly requested by the user.

        Returns
        -------
        Task
            Current immutable task snapshot.
        """
        ...
