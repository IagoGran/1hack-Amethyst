"""Application bindings and task-local execution state."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from amethyst.application.budgets import TokenBudget
from amethyst.application.timing import Deadline
from amethyst.domain.contracts import (
    Message,
    OperationContext,
    ProposedAction,
    StartTask,
    TaskEvent,
    ToolResult,
)
from amethyst.domain.tasks import Task
from amethyst.ports.tool import AgentTool


@dataclass(frozen=True, slots=True)
class ProviderBinding:
    provider: Any
    model_id: str
    enabled: bool = True
    context_tokens: int = 32_000


@dataclass(frozen=True, slots=True)
class ToolBinding:
    tool: AgentTool
    resource: str
    kind: str = "text"
    enabled: bool = True


@dataclass
class RunningTask:
    task: Task
    request: StartTask
    deadline: Deadline
    budget: TokenBudget
    events: list[TaskEvent] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    resume: asyncio.Event = field(default_factory=asyncio.Event)
    worker: asyncio.Task[None] | None = None
    messages: list[Message] = field(default_factory=list)
    partial_text: str = ""
    tool_signatures: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class PreparedOperation:
    action: ProposedAction | None
    execute: Callable[[str | None, OperationContext], Awaitable[ToolResult]]
