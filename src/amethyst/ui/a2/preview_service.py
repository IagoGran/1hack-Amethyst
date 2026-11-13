"""Controllable, in-memory task service for demonstrating A2 interactions."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import uuid4

from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    StartTask,
    TaskEvent,
    TaskEventPayload,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
)
from amethyst.domain.tasks import Task, TaskStatus


@dataclass
class PreviewTask:
    """Hold one fake task's state, event queue, and budget gate."""

    task: Task
    events: list[TaskEvent] = field(default_factory=list)
    queue: asyncio.Queue[TaskEvent | None] = field(default_factory=asyncio.Queue)
    budget_gate: asyncio.Event = field(default_factory=asyncio.Event)
    producer: asyncio.Task[None] | None = None


class A2PreviewService:
    """Run deterministic tasks without models, tools, files, or persistence."""

    def __init__(self) -> None:
        """Initialize the in-memory task registry for one preview session."""
        self._tasks: dict[str, PreviewTask] = {}

    async def start_task(self, request: StartTask) -> Task:
        """Create a task and start its simulated response producer."""
        task = Task(
            str(uuid4()), request.request, conversation_id=request.conversation_id
        )
        record = PreviewTask(task=task)
        self._tasks[task.id] = record
        record.producer = asyncio.create_task(
            self._produce(record, request.model_connection_id)
        )
        return task

    async def get_task(self, task_id: str) -> Task:
        """Return the latest task snapshot or a safe not-found error."""
        return self._record(task_id).task

    async def cancel_task(self, task_id: str) -> Task:
        """Cancel the producer and acknowledge only after it stops."""
        record = self._record(task_id)
        if record.producer and not record.producer.done():
            record.producer.cancel()
            try:
                await record.producer
            except asyncio.CancelledError:
                pass
        if record.task.status not in self._terminal_states():
            self._emit(record, TaskStateChanged(TaskStatus.CANCELLED))
            record.task = self._with_status(record.task, TaskStatus.CANCELLED)
            await record.queue.put(None)
        return record.task

    async def increase_budget(self, task_id: str, additional_tokens: int) -> Task:
        """Resume a budget-paused demo after an explicit positive increase."""
        record = self._record(task_id)
        if additional_tokens <= 0 or record.task.status != TaskStatus.PAUSED_FOR_BUDGET:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Budget increase is unavailable."
            )
        record.budget_gate.set()
        return record.task

    async def events(
        self, task_id: str, after_sequence: int = 0
    ) -> AsyncIterator[TaskEvent]:
        """Replay missed events, then follow the task until its terminal marker."""
        record = self._record(task_id)
        last_sequence = after_sequence
        for event in record.events:
            if event.sequence > last_sequence:
                last_sequence = event.sequence
                yield event
        if record.task.status in self._terminal_states():
            return
        while True:
            event = await record.queue.get()
            if event is None:
                return
            if event.sequence > last_sequence:
                last_sequence = event.sequence
                yield event

    async def _produce(self, record: PreviewTask, mode: str) -> None:
        """Emit a short fake response, pause, or safe failure by selected mode."""
        self._set_status(record, TaskStatus.RUNNING)
        if mode == "preview:failure":
            await asyncio.sleep(0.6)
            self._emit(
                record,
                TaskFailure(ErrorCode.UNAVAILABLE, "Preview scenario failed safely."),
            )
            self._set_status(record, TaskStatus.FAILED)
            await record.queue.put(None)
            return
        text = self._response_for(record.task.request)
        chunks = text.split(" ")
        for index, word in enumerate(chunks):
            if mode == "preview:budget" and index == len(chunks) // 2:
                self._set_status(record, TaskStatus.PAUSED_FOR_BUDGET)
                await record.budget_gate.wait()
                record.budget_gate.clear()
                self._set_status(
                    record, TaskStatus.RUNNING, "Budget increased by the user."
                )
            suffix = " " if index < len(chunks) - 1 else ""
            self._emit(record, TextDelta(word + suffix))
            await asyncio.sleep(0.22)
        self._set_status(record, TaskStatus.COMPLETED)
        await record.queue.put(None)

    def _emit(self, record: PreviewTask, payload: TaskEventPayload) -> None:
        """Assign the next sequence and publish a typed task event."""
        event = TaskEvent(record.task.id, len(record.events) + 1, payload)
        record.events.append(event)
        record.queue.put_nowait(event)

    def _set_status(
        self, record: PreviewTask, status: TaskStatus, message: str = ""
    ) -> None:
        """Update task state and emit its lifecycle transition."""
        record.task = self._with_status(record.task, status)
        self._emit(record, TaskStateChanged(status, message))

    @staticmethod
    def _with_status(task: Task, status: TaskStatus) -> Task:
        """Copy a task snapshot with its latest lifecycle state."""
        return Task(task.id, task.request, status, task.conversation_id)

    @staticmethod
    def _response_for(request: str) -> str:
        """Choose a local placeholder response for code and debugging prompts."""
        if "debug" in request.lower() or "error" in request.lower():
            return (
                "Debug preview: inspect the traceback, isolate the failing input, "
                "then add a regression check."
            )
        return (
            "Code generation preview: clarify the interface, outline a small "
            "implementation, then review the proposed changes."
        )

    @staticmethod
    def _terminal_states() -> set[TaskStatus]:
        """Return terminal task states used to close event streams."""
        return {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}

    def _record(self, task_id: str) -> PreviewTask:
        """Look up a task or raise a safe contract-level not-found error."""
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise ContractError(
                ErrorCode.NOT_FOUND, "Preview task was not found."
            ) from exc
