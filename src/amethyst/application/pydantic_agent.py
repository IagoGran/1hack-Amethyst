"""Run PydanticAI with Amethyst tools, history, budgets, and events."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from typing import Any, cast
from uuid import uuid4

from pydantic_ai import Agent, RunContext, Tool, UsageLimits, capture_run_messages
from pydantic_ai.messages import (
    ModelMessage,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.messages import ModelRequest as AIRequest
from pydantic_ai.messages import ModelResponse as AIResponse
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from amethyst.application.state import ProviderBinding, RunningTask
from amethyst.application.timing import retry_delay
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    Message,
    TextDelta,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from amethyst.domain.tasks import TaskStatus


class _ModelRequestFailure(Exception):
    """Keep model retry scope separate from failures raised by tool execution."""

    def __init__(self, error: ContractError) -> None:
        self.error = error


async def run_agent(
    service: Any,
    record: RunningTask,
    binding: ProviderBinding,
    instructions: str,
    title: str,
) -> None:
    """Run a native agent with bounded retries for transient model failures."""
    retries = service.limits.retries
    for attempt in range(retries + 1):
        try:
            await _run_agent_once(service, record, binding, instructions, title)
            return
        except _ModelRequestFailure as failure:
            error = failure.error
            delay = retry_delay(error, attempt, retries, safe=True)
            if delay is None:
                raise error from None
            record.budget.charge(error.usage, 0)
            if error.usage is not None:
                await service._emit(record, error.usage)
            record.partial_text = ""
            if delay:
                await asyncio.sleep(min(delay, record.deadline.remaining()))


async def _run_agent_once(
    service: Any,
    record: RunningTask,
    binding: ProviderBinding,
    instructions: str,
    title: str,
) -> None:
    """Run one native PydanticAI graph and persist its settled messages.

    Parameters
    ----------
    service : AgentService
        Application task/session owner.
    record : RunningTask
        Task-local state, messages, limits, and budget.
    binding : ProviderBinding
        Native PydanticAI model and configured context capacity.
    instructions : str
        System and selected skill instructions.
    title : str
        Conversation title used for persistence.

    Returns
    -------
    None
    """
    definitions = service._tool_dispatcher.definitions()
    tools = [_registered_tool(service, record, item) for item in definitions]
    settings = cast(
        ModelSettings,
        _model_settings(
            binding.context_tokens,
            service.limits.input_tokens,
            service.limits.output_tokens,
        ),
    )
    agent = Agent(
        cast(Model, binding.provider),
        instructions=instructions,
        tools=tools,
        model_settings=settings,
        retries=0,
    )
    history = to_ai_messages(record.messages)
    captured: list[ModelMessage] = []
    usage_limits = UsageLimits(request_limit=50)
    try:
        async with asyncio.timeout(record.deadline.remaining()):
            with capture_run_messages() as captured:
                async with agent.iter(
                    None,
                    message_history=history,
                    deps=(service, record),
                    usage_limits=usage_limits,
                ) as run:
                    async for node in run:
                        if Agent.is_model_request_node(node):
                            await _stream_model_node(
                                service, record, binding, run, node, definitions
                            )
        if run.result is None:
            raise ContractError(ErrorCode.UNAVAILABLE, "Agent produced no result.")
        record.messages = _redacted_messages(
            service, from_ai_messages(run.result.all_messages())
        )
        record.partial_text = ""
        await service._save(record, title)
    except TimeoutError as error:
        if captured:
            record.messages = _redacted_messages(service, from_ai_messages(captured))
            record.partial_text = ""
        raise ContractError(ErrorCode.TIMEOUT, "Task deadline exceeded.") from error
    except BaseException:
        if captured:
            record.messages = _redacted_messages(service, from_ai_messages(captured))
            record.partial_text = ""
        raise


def _registered_tool(
    service: Any, record: RunningTask, definition: ToolDefinition
) -> Tool[Any]:
    """Create schema-backed PydanticAI tools that delegate to ToolDispatcher.

    Parameters
    ----------
    service : AgentService
        Application task/session owner.
    record : RunningTask
        Task whose enabled capabilities are exposed.
    definition : ToolDefinition
        Enabled tool schema available for this run.

    Returns
    -------
    Tool
        PydanticAI tool registered for the run.
    """

    async def invoke(
        ctx: RunContext[tuple[Any, RunningTask]], **arguments: Any
    ) -> dict[str, Any]:
        """Validate, authorize, execute, and format a selected tool call.

        Parameters
        ----------
        ctx : RunContext
            PydanticAI context containing this call's unique ID.
        **arguments : Any
            Model-supplied JSON arguments validated by the dispatcher.

        Returns
        -------
        dict
            Bounded result data returned to the model.
        """
        owner, task = ctx.deps
        call = ToolCall(
            ctx.tool_call_id or uuid4().hex,
            definition.name,
            arguments,
        )
        _reject_repeat(task, call)
        _validate_schema(arguments, definition.input_schema)
        result = await owner._tool_dispatcher.execute(task, call)
        await owner._emit(task, result)
        return _tool_payload(result)

    def validate_arguments(*args: Any, **kwargs: Any) -> None:
        """Validate either mapping or keyword arguments from PydanticAI."""
        values = kwargs if kwargs else (args[0] if args else {})
        _validate_schema(values, definition.input_schema)

    return Tool.from_schema(
        invoke,
        name=definition.name,
        description=definition.description,
        json_schema=definition.input_schema,
        takes_ctx=True,
        sequential=True,
        args_validator=validate_arguments,
    )


def _reject_repeat(record: RunningTask, call: ToolCall) -> None:
    """Stop an identical tool request from repeating within one task.

    Parameters
    ----------
    record : RunningTask
        Task-local state with previously completed tool requests.
    call : ToolCall
        Current requested operation.

    Returns
    -------
    None
    """
    signature = json.dumps(
        [call.name, call.arguments], sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(signature.encode()).hexdigest()
    if digest in record.tool_signatures:
        raise ContractError(
            ErrorCode.CONFLICT, "Repeated tool call made no new progress."
        )
    record.tool_signatures.add(digest)


def _tool_payload(result: ToolResult) -> dict[str, Any]:
    """Return bounded tool output as structured data for the model.

    Parameters
    ----------
    result : ToolResult
        Authorized, redacted result from the dispatcher.

    Returns
    -------
    dict
        JSON-compatible response containing content and attribution.
    """
    return {
        "content": result.content,
        "sources": [asdict(source) for source in result.sources],
        "truncated": result.truncated,
    }


def _validate_schema(
    value: Any, schema: dict[str, Any], path: str = "arguments"
) -> None:
    """Validate the JSON Schema subset used by configured Amethyst tools.

    Parameters
    ----------
    value : Any
        Model-supplied argument value.
    schema : dict
        Tool's declared JSON Schema.
    path : str
        Current object path used in safe validation errors.

    Returns
    -------
    None

    Raises
    ------
    ContractError
        If the value does not match the supported schema constraints.
    """
    expected = schema.get("type")
    allowed_types = expected if isinstance(expected, list) else [expected]
    if expected and not any(_matches_type(value, kind) for kind in allowed_types):
        raise ContractError(ErrorCode.INVALID_INPUT, f"Invalid {path} type.")
    if isinstance(value, dict):
        required = schema.get("required", [])
        if any(name not in value for name in required):
            raise ContractError(ErrorCode.INVALID_INPUT, f"Missing required {path}.")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ContractError(ErrorCode.INVALID_INPUT, f"Unexpected {path} field.")
        for name, child in value.items():
            if name in properties:
                _validate_schema(child, properties[name], f"{path}.{name}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(ErrorCode.INVALID_INPUT, f"Invalid {path} value.")


def _matches_type(value: Any, kind: Any) -> bool:
    """Check one JSON Schema primitive type without treating booleans as numbers.

    Parameters
    ----------
    value : Any
        Candidate JSON value.
    kind : Any
        JSON Schema type name.

    Returns
    -------
    bool
        Whether the value matches the stated JSON primitive type.
    """
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: (
            isinstance(item, int | float) and not isinstance(item, bool)
        ),
        "null": lambda item: item is None,
    }
    return bool(checks.get(kind, lambda _item: True)(value))


async def _stream_model_node(
    service: Any,
    record: RunningTask,
    binding: ProviderBinding,
    run: Any,
    node: Any,
    definitions: tuple[ToolDefinition, ...],
) -> None:
    """Reserve task budget, stream a PydanticAI request, and emit usage.

    Parameters
    ----------
    service : AgentService
        Application task/session owner.
    record : RunningTask
        Task-local budget and event channel.
    binding : ProviderBinding
        Model context capacity for this request.
    run : AgentRun
        PydanticAI graph execution.
    node : ModelRequestNode
        Current native model request node.
    definitions : tuple[ToolDefinition, ...]
        Tool schemas included in the conservative input estimate.

    Returns
    -------
    None
    """
    input_bound = _request_input_bound(node, definitions)
    if input_bound > service.limits.input_tokens:
        raise ContractError(ErrorCode.INVALID_INPUT, "Model input limit exceeded.")
    if input_bound + 1 > binding.context_tokens:
        raise ContractError(ErrorCode.INVALID_INPUT, "Model context capacity exceeded.")
    output_limit = min(
        service.limits.output_tokens, binding.context_tokens - input_bound
    )
    reserved = input_bound + output_limit
    await _reserve_budget(service, record, reserved)
    before = _usage_counts(run.ctx.state.usage)
    timeout = min(service.limits.model_total_seconds, record.deadline.remaining())
    try:
        async with asyncio.timeout(timeout):
            stream_context = node.stream(run.ctx)
            try:
                async with asyncio.timeout(service.limits.model_idle_seconds):
                    stream = await stream_context.__aenter__()
            except TimeoutError as error:
                raise ContractError(
                    ErrorCode.TIMEOUT, "Model response timed out."
                ) from error
            try:
                text_stream = stream.stream_text(delta=True)
                while True:
                    pending = asyncio.create_task(anext(text_stream))
                    done, _ = await asyncio.wait(
                        {pending}, timeout=service.limits.model_idle_seconds
                    )
                    if not done:
                        await stream.cancel()
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
                        raise ContractError(
                            ErrorCode.TIMEOUT, "Model response timed out."
                        )
                    try:
                        event = pending.result()
                    except StopAsyncIteration:
                        break
                    if event:
                        safe = service.redactor.redact(event)
                        record.partial_text += safe
                        await service._emit(record, _text_delta(safe))
            except BaseException as error:
                await stream_context.__aexit__(type(error), error, error.__traceback__)
                raise
            else:
                await stream_context.__aexit__(None, None, None)
    except ContractError as error:
        raise _ModelRequestFailure(error) from error
    except TimeoutError as error:
        raise _ModelRequestFailure(
            ContractError(ErrorCode.TIMEOUT, "Model response timed out.")
        ) from error
    except Exception as error:
        status = getattr(error, "status_code", None)
        authenticated = status in {401, 403}
        retryable = status in {408, 429} or (isinstance(status, int) and status >= 500)
        code = ErrorCode.AUTHENTICATION if authenticated else ErrorCode.UNAVAILABLE
        message = (
            "Model provider authentication failed."
            if authenticated
            else "Model provider request failed."
        )
        raise _ModelRequestFailure(
            ContractError(code, message, transient=retryable)
        ) from error
    after = _usage_counts(run.ctx.state.usage)
    input_tokens, output_tokens = after[0] - before[0], after[1] - before[1]
    actual = (
        Usage(input_tokens, output_tokens)
        if input_tokens > 0 or output_tokens > 0
        else None
    )
    usage = record.budget.charge(actual, reserved)
    await service._emit(record, usage)


def _text_delta(text: str):
    """Create the domain text event without leaking model framework types.

    Parameters
    ----------
    text : str
        Redacted response fragment.

    Returns
    -------
    TextDelta
        User-visible incremental response event.
    """
    return TextDelta(text)


def _request_input_bound(node: Any, definitions: tuple[ToolDefinition, ...]) -> int:
    """Estimate one model request's input from messages and exposed schemas.

    Parameters
    ----------
    node : ModelRequestNode
        Current PydanticAI request and message context.
    definitions : tuple[ToolDefinition, ...]
        Schemas made available to this agent run.

    Returns
    -------
    int
        Conservative byte-based token estimate including fixed framing.
    """
    body = json.dumps(
        {"request": str(node.request), "tools": [asdict(item) for item in definitions]},
        ensure_ascii=False,
    )
    return len(body.encode("utf-8")) + 128


def _model_settings(context_limit: int, input_limit: int, output_limit: int):
    """Return per-request native model settings bounded by configured capacity.

    Parameters
    ----------
    context_limit : int
        Configured model context window.
    input_limit : int
        Configured per-request input ceiling.
    output_limit : int
        Configured per-request output ceiling.

    Returns
    -------
    Callable
        PydanticAI model settings resolver that reserves output capacity.
    """

    def resolve(ctx: RunContext[Any]) -> dict[str, int]:
        """Set maximum output tokens after reserving current message context.

        Parameters
        ----------
        ctx : RunContext
            Current messages about to be sent to the selected model.

        Returns
        -------
        dict
            Maximum output tokens for this model request.
        """
        estimated_input = len(str(ctx.messages).encode("utf-8")) + 128
        if estimated_input > input_limit:
            raise ContractError(ErrorCode.INVALID_INPUT, "Model input limit exceeded.")
        available = context_limit - estimated_input
        if available <= 0:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Model context capacity exceeded."
            )
        return {"max_tokens": min(output_limit, available)}

    return resolve


async def _reserve_budget(service: Any, record: RunningTask, tokens: int) -> None:
    """Pause before a model request until its reservation fits the task budget.

    Parameters
    ----------
    service : AgentService
        Task owner used to publish visible state changes.
    record : RunningTask
        Budget and explicit resume signal.
    tokens : int
        Conservative input-plus-output request reservation.

    Returns
    -------
    None
    """
    while not record.budget.can_reserve(tokens):
        record.resume.clear()
        await service._state(
            record,
            TaskStatus.PAUSED_FOR_BUDGET,
            "Increase the token budget to continue.",
        )
        await record.deadline.run(record.resume.wait, record.deadline.remaining())
    if record.task.status == TaskStatus.PAUSED_FOR_BUDGET:
        await service._state(record, TaskStatus.RUNNING, "Token budget increased.")


def _usage_counts(usage: Any) -> tuple[int, int]:
    """Read provider-reported cumulative token counts from a PydanticAI run.

    Parameters
    ----------
    usage : RunUsage
        Usage currently accumulated by the native run.

    Returns
    -------
    tuple of int
        Cumulative input and output token counts.
    """
    return int(usage.input_tokens or 0), int(usage.output_tokens or 0)


def to_ai_messages(messages: list[Message]) -> list[ModelMessage]:
    """Translate Amethyst's persisted history into PydanticAI messages.

    Parameters
    ----------
    messages : list[Message]
        Retained conversation messages, including the current user turn.

    Returns
    -------
    list of ModelMessage
        Native history preserving tool call and result identifiers.
    """
    converted: list[ModelMessage] = []
    call_names: dict[str, str] = {}
    for message in messages:
        if message.role == "system":
            converted.append(AIRequest([SystemPromptPart(message.content)]))
        elif message.role == "user":
            converted.append(AIRequest([UserPromptPart(message.content)]))
        elif message.role == "assistant":
            parts: list[Any] = [TextPart(message.content)] if message.content else []
            for call in message.tool_calls:
                call_names[call.id] = call.name
                parts.append(
                    ToolCallPart(
                        tool_name=call.name,
                        args=call.arguments,
                        tool_call_id=call.id,
                    )
                )
            if parts:
                converted.append(AIResponse(parts=parts))
        elif message.role == "tool" and message.tool_call_id:
            name = call_names.get(message.tool_call_id, "unknown")
            converted.append(
                AIRequest(
                    [
                        ToolReturnPart(
                            tool_name=name,
                            tool_call_id=message.tool_call_id,
                            content=message.content,
                        )
                    ]
                )
            )
    return converted


def _remove_orphan_calls(messages: list[Message]) -> list[Message]:
    """Drop tool calls whose execution did not produce a persisted result.

    Parameters
    ----------
    messages : list[Message]
        Converted history from a complete or interrupted run.

    Returns
    -------
    list of Message
        History without unanswered calls that could be repeated on resume.
    """
    returned = {
        message.tool_call_id
        for message in messages
        if message.role == "tool" and message.tool_call_id
    }
    cleaned: list[Message] = []
    for message in messages:
        if message.role != "assistant" or not message.tool_calls:
            cleaned.append(message)
            continue
        calls = tuple(call for call in message.tool_calls if call.id in returned)
        if message.content or calls:
            cleaned.append(Message("assistant", message.content, tool_calls=calls))
    return cleaned


def _redacted_messages(service: Any, messages: list[Message]) -> list[Message]:
    """Redact text before translated model history reaches conversation storage.

    Parameters
    ----------
    service : AgentService
        Application owner providing the shared secret redactor.
    messages : list[Message]
        Translated PydanticAI message history.

    Returns
    -------
    list[Message]
        History with text content redacted.
    """
    return [
        replace(message, content=service.redactor.redact(message.content))
        for message in messages
    ]


def from_ai_messages(messages: list[ModelMessage]) -> list[Message]:
    """Translate PydanticAI history into Amethyst's retained message format.

    Parameters
    ----------
    messages : list of ModelMessage
        Native run history after success, failure, or cancellation.

    Returns
    -------
    list of Message
        Persistable messages preserving successful calls and returns.
    """
    converted: list[Message] = []
    for message in messages:
        if isinstance(message, AIRequest):
            _convert_request(message, converted)
        elif isinstance(message, AIResponse):
            _convert_response(message, converted)
    return _remove_orphan_calls(converted)


def _convert_request(message: AIRequest, output: list[Message]) -> None:
    """Append user and tool-return parts from one PydanticAI request.

    Parameters
    ----------
    message : ModelRequest
        Native model request message.
    output : list[Message]
        Amethyst history being assembled.

    Returns
    -------
    None
    """
    for part in message.parts:
        if isinstance(part, UserPromptPart):
            output.append(Message("user", _as_text(part.content)))
        elif isinstance(part, ToolReturnPart):
            output.append(Message("tool", _as_text(part.content), part.tool_call_id))


def _convert_response(message: AIResponse, output: list[Message]) -> None:
    """Append assistant text and structured calls from one model response.

    Parameters
    ----------
    message : ModelResponse
        Native assistant response.
    output : list[Message]
        Amethyst history being assembled.

    Returns
    -------
    None
    """
    texts = [part.content for part in message.parts if isinstance(part, TextPart)]
    calls = tuple(
        ToolCall(part.tool_call_id, part.tool_name, _call_args(part.args))
        for part in message.parts
        if isinstance(part, ToolCallPart)
    )
    content = "".join(texts)
    if content or calls:
        output.append(Message("assistant", content, tool_calls=calls))


def _as_text(value: Any) -> str:
    """Convert structured message content into the persisted string contract.

    Parameters
    ----------
    value : Any
        Text or structured PydanticAI message content.

    Returns
    -------
    str
        Plain text or compact JSON representation.
    """
    return value if isinstance(value, str) else json.dumps(value, default=str)


def _call_args(value: Any) -> dict[str, Any]:
    """Normalize a PydanticAI tool call's validated argument mapping.

    Parameters
    ----------
    value : Any
        Structured or JSON-encoded tool arguments.

    Returns
    -------
    dict
        Tool arguments conforming to the domain contract.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ContractError(ErrorCode.INVALID_INPUT, "Invalid tool arguments.")
