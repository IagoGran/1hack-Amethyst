"""Explicit development doubles. Never wire these as production integrations."""

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import replace
from typing import Protocol

from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    ModelCapabilities,
    ModelCompleted,
    ModelEvent,
    ModelRequest,
    OperationContext,
    StartTask,
    TaskEvent,
    TaskEventPayload,
    TaskStateChanged,
    TextDelta,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from amethyst.domain.tasks import Task, TaskStatus


class FakeModelProvider:
    def __init__(self, chunks: tuple[str, ...] = ("Fake ", "response.")) -> None:
        self.chunks = chunks

    async def capabilities(self, model_id: str) -> ModelCapabilities:
        return ModelCapabilities(
            streaming=True, tool_calls=False, context_tokens=40_000
        )

    async def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield TextDelta(chunk)
        # Fixed fixture usage, not a tokenizer or real billing measurement.
        yield ModelCompleted(Usage(input_tokens=4, output_tokens=len(self.chunks)))


class FakeTool:
    def __init__(self, content: str = "Fake tool result.") -> None:
        self.content = content

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition("fake.read", "Returns a fixture without external access.")

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        if call.name != self.definition.name:
            raise ContractError(ErrorCode.INVALID_INPUT, "Unknown fake tool.")
        await asyncio.sleep(0)
        encoded = self.content.encode("utf-8")
        bounded = encoded[: max(0, context.output_limit_bytes)]
        return ToolResult(
            call.id,
            bounded.decode("utf-8", errors="ignore"),
            truncated=len(bounded) < len(encoded),
        )

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        return ConnectionHealth(True, "Fake connection; no external service contacted.")


class Identified(Protocol):
    @property
    def id(self) -> str: ...


class InMemoryRepository[T: Identified]:
    """Detached snapshots, intentionally lost when this instance is discarded."""

    def __init__(self) -> None:
        self._values: dict[str, T] = {}

    async def save(self, value: T) -> None:
        self._values[value.id] = deepcopy(value)

    async def load(self, item_id: str) -> T:
        try:
            return deepcopy(self._values[item_id])
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, "Record not found.") from None

    async def list(self) -> tuple[T, ...]:
        return tuple(deepcopy(self._values[key]) for key in sorted(self._values))

    async def delete(self, item_id: str) -> None:
        self._values.pop(item_id, None)


class MemoryCredentialStore:
    """Development-only, memory-only credential double with no disk fallback."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    async def get(self, reference: str) -> str | None:
        return self._secrets.get(reference)

    async def set(self, reference: str, secret: str) -> None:
        self._secrets[reference] = secret

    async def delete(self, reference: str) -> None:
        self._secrets.pop(reference, None)

    def clear(self) -> None:
        self._secrets.clear()


class FakeApplicationService:
    """Replayable task fixture; no models, tools, file access, or persistence.

    Each task completes on the event loop independently of event subscribers.
    Budget and approval workflows remain unavailable until B implements them.
    """

    def __init__(self, chunks: tuple[str, ...] = ("Fake response.",)) -> None:
        self._chunks = chunks
        self._tasks: dict[str, Task] = {}
        self._events: dict[str, list[TaskEvent]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}

    async def start_task(self, request: StartTask) -> Task:
        if not request.request.strip() or not request.conversation_id:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "A conversation and text are required."
            )
        task_id = f"fake-task-{len(self._tasks) + 1}"
        task = Task(task_id, request.request, conversation_id=request.conversation_id)
        self._tasks[task_id] = task
        self._events[task_id] = []
        self._conditions[task_id] = asyncio.Condition()
        await self._emit(task_id, TaskStateChanged(TaskStatus.PENDING))
        self._workers[task_id] = asyncio.create_task(self._run(task_id))
        return task

    async def _emit(self, task_id: str, payload: TaskEventPayload) -> None:
        async with self._conditions[task_id]:
            if isinstance(payload, TaskStateChanged):
                self._tasks[task_id] = replace(
                    self._tasks[task_id], status=payload.status
                )
            history = self._events[task_id]
            history.append(TaskEvent(task_id, len(history) + 1, payload))
            self._conditions[task_id].notify_all()

    async def _run(self, task_id: str) -> None:
        await self._emit(task_id, TaskStateChanged(TaskStatus.RUNNING))
        for chunk in self._chunks:
            await asyncio.sleep(0)
            await self._emit(task_id, TextDelta(chunk))
        await self._emit(task_id, TaskStateChanged(TaskStatus.COMPLETED))

    async def get_task(self, task_id: str) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, "Task not found.") from None

    async def events(
        self, task_id: str, after_sequence: int = 0
    ) -> AsyncIterator[TaskEvent]:
        await self.get_task(task_id)
        if after_sequence < 0:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Event cursor cannot be negative."
            )
        cursor = after_sequence
        terminal = {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}
        while True:
            async with self._conditions[task_id]:
                while (
                    len(self._events[task_id]) <= cursor
                    and self._tasks[task_id].status not in terminal
                ):
                    await self._conditions[task_id].wait()
                pending = tuple(self._events[task_id][cursor:])
                finished = self._tasks[task_id].status in terminal
            for event in pending:
                cursor = event.sequence
                yield event
            if finished:
                return

    async def cancel_task(self, task_id: str) -> Task:
        task = await self.get_task(task_id)
        if task.status in {
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        }:
            return task
        worker = self._workers[task_id]
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        await self._emit(task_id, TaskStateChanged(TaskStatus.CANCELLED))
        return self._tasks[task_id]

    async def increase_budget(self, task_id: str, additional_tokens: int) -> Task:
        await self.get_task(task_id)
        if additional_tokens <= 0:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Budget increase must be positive."
            )
        raise ContractError(
            ErrorCode.UNAVAILABLE, "Budget simulation is not implemented."
        )
