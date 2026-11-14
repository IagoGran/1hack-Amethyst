"""Model request limits, streaming, accounting, and safe retry coordination."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, replace
from functools import partial
from typing import TYPE_CHECKING
from uuid import uuid4

from amethyst.application.budgets import request_tokens, token_bound
from amethyst.application.state import ProviderBinding, RunningTask
from amethyst.application.timing import retry_delay
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    Message,
    ModelCompleted,
    ModelEvent,
    ModelRequest,
    TextDelta,
    ToolCall,
    ToolDefinition,
    Usage,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.security.redaction import StreamRedactor

if TYPE_CHECKING:
    from amethyst.application.service import AgentService


def _starts_json_object(text: str) -> bool:
    """Check whether buffered output may be a textual function-call object.

    Parameters
    ----------
    text : str
        Accumulated model output.

    Returns
    -------
    bool
        Whether the response begins with a JSON object candidate.
    """
    stripped = text.lstrip()
    return not stripped or stripped.startswith("{")


def _text_tool_call(text: str, tools: tuple[ToolDefinition, ...]) -> ToolCall | None:
    """Decode a strict textual tool envelope for an enabled tool only.

    Parameters
    ----------
    text : str
        Complete buffered JSON response.
    tools : tuple[ToolDefinition, ...]
        Enabled tools from the current bounded model request.

    Returns
    -------
    ToolCall or None
        Recovered call, or None when the text is ordinary output.
    """
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    arguments = payload.get("arguments") if isinstance(payload, dict) else None
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"name", "arguments"}
        or not isinstance(payload["name"], str)
        or not isinstance(arguments, dict)
        or payload["name"] not in {tool.name for tool in tools}
    ):
        return None
    return ToolCall(uuid4().hex, payload["name"], arguments)


@dataclass
class ModelAttempt:
    """Keep one attempt's output, accounting, and visibility together."""

    estimated: int
    output_limit: int
    sanitizer: StreamRedactor
    text: str = ""
    pending_text: str = ""
    completed: ModelCompleted | None = None
    charged: bool = False
    visible: bool = False

    @property
    def reserved(self) -> int:
        """Return the combined input and output reservation.

        Parameters
        ----------
        None

        Returns
        -------
        int
            Maximum token charge for unknown usage.
        """
        return self.estimated + self.output_limit


class ModelRunner:
    """Generate model events without preparing or executing tool calls."""

    def __init__(self, agent: AgentService) -> None:
        """Bind the session's event, budget, and deadline services.

        Parameters
        ----------
        agent : AgentService
            Task orchestrator that owns all application state.

        Returns
        -------
        None
        """
        self.agent = agent

    async def generate(
        self, record: RunningTask, binding: ProviderBinding, instructions: str
    ) -> tuple[str, ModelCompleted]:
        """Build a bounded request and retry only before output becomes visible.

        Parameters
        ----------
        record : RunningTask
            Task-local conversation, deadline, and budget.
        binding : ProviderBinding
            Selected model provider and model identifier.
        instructions : str
            System and selected skill instructions.

        Returns
        -------
        tuple of str and ModelCompleted
            Redacted response and validated completion metadata.
        """
        request, estimated = await self._request(record, binding, instructions)
        for attempt in range(self.agent.limits.retries + 1):
            state = ModelAttempt(
                estimated,
                request.max_output_tokens,
                StreamRedactor(self.agent.redactor),
            )
            await self._reserve(record, state.reserved)
            try:
                return await self._attempt(record, binding, request, state)
            except ContractError as error:
                delay = retry_delay(
                    error, attempt, self.agent.limits.retries, safe=not state.visible
                )
                if delay is None:
                    raise
                record.partial_text = ""
                await self.agent._state(
                    record, TaskStatus.RUNNING, "Retrying a transient model failure."
                )
                await record.deadline.run(
                    partial(asyncio.sleep, delay), record.deadline.remaining()
                )
        raise AssertionError("Retry loop exhausted without an outcome")

    async def _request(
        self, record: RunningTask, binding: ProviderBinding, instructions: str
    ) -> tuple[ModelRequest, int]:
        """Reserve output that fits both configured limits and model capacity.

        Parameters
        ----------
        record : RunningTask
            Current conversation and deadline.
        binding : ProviderBinding
            Selected model configuration.
        instructions : str
            System instructions for the request.

        Returns
        -------
        tuple of ModelRequest and int
            Capacity-checked request and estimated input tokens.
        """
        limits = self.agent.limits
        capabilities = await record.deadline.run(
            lambda: binding.provider.capabilities(binding.model_id), limits.tool_seconds
        )
        request = ModelRequest(
            binding.model_id,
            (Message("system", instructions), *record.messages),
            self.agent._tool_dispatcher.definitions()
            if capabilities.tool_calls
            else (),
            limits.input_tokens,
            limits.output_tokens,
            limits.model_idle_seconds,
            limits.model_total_seconds,
        )
        estimated = request_tokens(request)
        output_limit = min(
            limits.output_tokens, capabilities.context_tokens - estimated
        )
        if estimated > limits.input_tokens or output_limit <= 0:
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Conversation exceeds model input or context capacity.",
            )
        return replace(request, max_output_tokens=output_limit), estimated

    async def _reserve(self, record: RunningTask, tokens: int) -> None:
        """Pause until the user explicitly increases an exhausted task budget.

        Parameters
        ----------
        record : RunningTask
            Task state and budget resume signal.
        tokens : int
            Tokens needed before starting the next model attempt.

        Returns
        -------
        None
        """
        while not record.budget.can_reserve(tokens):
            record.resume.clear()
            await self.agent._state(
                record,
                TaskStatus.PAUSED_FOR_BUDGET,
                "Increase the token budget to continue.",
            )
            await record.deadline.run(record.resume.wait, record.deadline.remaining())
        if record.task.status == TaskStatus.PAUSED_FOR_BUDGET:
            await self.agent._state(
                record, TaskStatus.RUNNING, "Token budget increased."
            )

    async def _attempt(
        self,
        record: RunningTask,
        binding: ProviderBinding,
        request: ModelRequest,
        state: ModelAttempt,
    ) -> tuple[str, ModelCompleted]:
        """Account for one model attempt and always close its stream.

        Parameters
        ----------
        record : RunningTask
            Task budget and partial output.
        binding : ProviderBinding
            Selected model provider.
        request : ModelRequest
            Capacity-checked request.
        state : ModelAttempt
            Mutable accounting and output for this attempt.

        Returns
        -------
        tuple of str and ModelCompleted
            Redacted text and validated provider completion.
        """
        context = self.agent._context(record, self.agent.limits.model_total_seconds)
        stream = binding.provider.stream(request, context)
        try:
            async with asyncio.timeout(context.timeout_seconds):
                await self._consume(record, stream, state, request.tools)
            if state.completed is None:
                raise ContractError(
                    ErrorCode.UNAVAILABLE, "Model stream ended without a completion."
                )
            state.charged = True
            usage = record.budget.charge(state.completed.usage, state.reserved)
            await self.agent._emit(record, usage)
            self._validate_completion(state, usage)
            remaining = state.sanitizer.finish()
            if remaining:
                await self.agent._emit(record, TextDelta(remaining))
            return self.agent.redactor.redact(state.text), state.completed
        except (TimeoutError, ContractError) as raw:
            error = (
                raw
                if isinstance(raw, ContractError)
                else ContractError(
                    ErrorCode.TIMEOUT, "Model request timed out.", transient=True
                )
            )
            if not state.charged:
                state.charged = True
                usage = record.budget.charge(
                    state.completed.usage if state.completed else error.usage,
                    state.reserved,
                )
                await self.agent._emit(record, usage)
            raise error from None
        finally:
            if not state.charged:
                usage = record.budget.charge(None, state.reserved)
                await self.agent._emit(record, usage)
            closer = getattr(stream, "aclose", None)
            if closer is not None:
                async with asyncio.timeout(self.agent.limits.tool_seconds):
                    await closer()

    async def _consume(
        self,
        record: RunningTask,
        stream: AsyncIterator[ModelEvent],
        state: ModelAttempt,
        tools: tuple[ToolDefinition, ...],
    ) -> None:
        """Validate stream ordering and publish redacted deltas within limits.

        Parameters
        ----------
        record : RunningTask
            Task receiving partial output and UI events.
        stream : AsyncIterator of ModelEvent
            Provider stream for this attempt.
        state : ModelAttempt
            Collected output and completion state.
        tools : tuple[ToolDefinition, ...]
            Enabled tools available to the current model request.

        Returns
        -------
        None
        """
        while True:
            try:
                event = await asyncio.wait_for(
                    anext(stream), self.agent.limits.model_idle_seconds
                )
            except StopAsyncIteration:
                return
            if state.completed is not None:
                raise ContractError(
                    ErrorCode.INVALID_INPUT, "Provider emitted data after completion."
                )
            if isinstance(event, TextDelta):
                prior_text = state.text
                state.text += event.text
                record.partial_text = state.text
                if token_bound(state.text) > state.output_limit:
                    raise ContractError(
                        ErrorCode.INVALID_INPUT,
                        "Model output exceeds the reserved limit.",
                    )
                candidate = state.pending_text + event.text
                if (
                    _starts_json_object(candidate)
                    and not state.visible
                    and (not prior_text.strip() or state.pending_text)
                ):
                    state.pending_text = candidate
                else:
                    candidate = state.pending_text + event.text
                    state.pending_text = ""
                    await self._publish_text(record, state, candidate)
            elif isinstance(event, ModelCompleted):
                state.completed = event
                await self._finish_pending_text(record, state, tools)
            else:
                raise ContractError(ErrorCode.INVALID_INPUT, "Invalid model event.")

    async def _finish_pending_text(
        self,
        record: RunningTask,
        state: ModelAttempt,
        tools: tuple[ToolDefinition, ...],
    ) -> None:
        """Recover a textual tool envelope or publish ordinary buffered text.

        Parameters
        ----------
        record : RunningTask
            Task receiving visible model text.
        state : ModelAttempt
            Current response and held candidate text.
        tools : tuple[ToolDefinition, ...]
            Enabled tools that may be called in this request.

        Returns
        -------
        None
        """
        if not state.pending_text:
            return
        recovered = (
            _text_tool_call(state.pending_text, tools)
            if not state.completed or not state.completed.tool_calls
            else None
        )
        if recovered is not None and state.completed is not None:
            state.completed = replace(
                state.completed,
                tool_calls=(*state.completed.tool_calls, recovered),
                finish_reason="tool_calls",
            )
            state.text = ""
            record.partial_text = ""
        else:
            await self._publish_text(record, state, state.pending_text)
        state.pending_text = ""

    async def _publish_text(
        self, record: RunningTask, state: ModelAttempt, text: str
    ) -> None:
        """Redact and publish text that is not a structured tool envelope.

        Parameters
        ----------
        record : RunningTask
            Task receiving streamed model text.
        state : ModelAttempt
            Stream sanitizer and visibility state.
        text : str
            Raw text fragment or buffered response.

        Returns
        -------
        None
        """
        safe_text = state.sanitizer.feed(text)
        if safe_text:
            state.visible = True
            await self.agent._emit(record, TextDelta(safe_text))

    def _validate_completion(self, state: ModelAttempt, usage: Usage) -> None:
        """Reject excessive usage and tool arguments containing protected secrets.

        Parameters
        ----------
        state : ModelAttempt
            Completed attempt with reserved limits.
        usage : Usage
            Charged usage from the provider or conservative fallback.

        Returns
        -------
        None
        """
        assert state.completed is not None
        calls = state.completed.tool_calls
        if (
            usage.input_tokens > state.estimated
            or usage.output_tokens > state.output_limit
            or calls
            and token_bound(json.dumps([asdict(c) for c in calls]))
            + token_bound(state.text)
            > state.output_limit
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Provider exceeded the reserved token limits.",
                usage=Usage(),
            )
        for call in calls:
            serialized = json.dumps(asdict(call))
            if self.agent.redactor.redact(serialized) != serialized:
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED,
                    "Model tool arguments contain protected credentials.",
                    usage=Usage(),
                )
