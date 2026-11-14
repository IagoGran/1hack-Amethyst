"""PydanticAI FunctionModel wrapper for legacy protocol test fixtures."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.usage import RequestUsage

from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    Message,
    ModelCompleted,
    ModelRequest,
    OperationContext,
    TextDelta,
    ToolCall,
)


def pydantic_model(
    provider: Any, *, input_tokens: int = 32_000, output_tokens: int = 8_000
) -> FunctionModel:
    """Adapt a deterministic provider double to PydanticAI's test model.

    Parameters
    ----------
    provider : Any
        Legacy protocol fixture used by existing application tests.
    input_tokens : int
        Maximum input tokens allowed by the deterministic fixture.
    output_tokens : int
        Maximum output tokens allowed by the deterministic fixture.

    Returns
    -------
    FunctionModel
        Native PydanticAI model that preserves the fixture's scripted calls.
    """

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """Produce one PydanticAI response from the fixture's scripted stream.

        Parameters
        ----------
        messages : list of ModelMessage
            Full native conversation history.
        info : AgentInfo
            Enabled tool schemas supplied to the current request.

        Returns
        -------
        ModelResponse
            Scripted text and tool calls.
        """
        request, events, completion = await _collect(
            provider, messages, info, input_tokens, output_tokens
        )
        parts: list[Any] = [
            TextPart(event.text) for event in events if isinstance(event, TextDelta)
        ]
        parts.extend(
            ToolCallPart(call.name, call.arguments, tool_call_id=call.id)
            for call in completion.tool_calls
        )
        usage = completion.usage
        return ModelResponse(
            parts=parts,
            usage=RequestUsage(
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
            ),
        )

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        """Stream the scripted response through PydanticAI's native graph.

        Parameters
        ----------
        messages : list of ModelMessage
            Full native conversation history.
        info : AgentInfo
            Enabled tool schemas supplied to the current request.

        Yields
        ------
        str or dict
            Text fragments or one complete native tool-call delta mapping.
        """
        _, events, completion = await _collect(
            provider, messages, info, input_tokens, output_tokens
        )
        for event in events:
            if isinstance(event, TextDelta):
                yield event.text
        if completion.tool_calls:
            yield {
                index: DeltaToolCall(
                    name=call.name,
                    json_args=json.dumps(call.arguments),
                    tool_call_id=call.id,
                )
                for index, call in enumerate(completion.tool_calls)
            }

    return FunctionModel(respond, stream_function=stream)


async def _collect(
    provider: Any,
    messages: list[ModelMessage],
    info: AgentInfo,
    input_tokens: int,
    output_tokens: int,
) -> tuple[ModelRequest, list[Any], ModelCompleted]:
    """Read and validate one scripted response before adapting its events.

    Parameters
    ----------
    provider : Any
        Legacy model fixture.
    messages : list of ModelMessage
        Current native message history.
    info : AgentInfo
        Tool schemas sent to the fixture.
    input_tokens : int
        Configured request input limit.
    output_tokens : int
        Configured request output limit.

    Returns
    -------
    tuple
        Request, scripted events, and validated completion.
    """
    request = _request(messages, info, input_tokens, output_tokens)
    events = [
        event
        async for event in provider.stream(
            request, OperationContext("fixture", "fixture")
        )
    ]
    completion_index = next(
        (
            index
            for index, event in enumerate(events)
            if isinstance(event, ModelCompleted)
        ),
        None,
    )
    if completion_index is None:
        raise RuntimeError("Fixture model ended without a completion event.")
    completion = events[completion_index]
    if not isinstance(completion, ModelCompleted):
        raise ContractError(ErrorCode.INVALID_INPUT, "Invalid fixture completion.")
    if completion_index != len(events) - 1:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Fixture data followed completion."
        )
    if completion.usage and (
        completion.usage.input_tokens > input_tokens
        or completion.usage.output_tokens > output_tokens
    ):
        raise ContractError(ErrorCode.INVALID_INPUT, "Fixture usage exceeded limits.")
    response_text = "".join(
        event.text for event in events if isinstance(event, TextDelta)
    )
    if len(response_text.encode("utf-8")) > output_tokens:
        raise ContractError(ErrorCode.INVALID_INPUT, "Fixture output exceeded limits.")
    return request, events, completion


def _request(
    messages: list[ModelMessage],
    info: AgentInfo,
    input_tokens: int,
    output_tokens: int,
) -> ModelRequest:
    """Translate native messages and tool schemas for a protocol fixture.

    Parameters
    ----------
    messages : list of ModelMessage
        PydanticAI history.
    info : AgentInfo
        Registered model-facing tool definitions.

    Returns
    -------
    ModelRequest
        Fixture-compatible request contract.
    """
    converted: list[Message] = []
    if info.instructions:
        converted.append(Message("system", info.instructions))
    for message in messages:
        texts: list[str] = []
        calls: list[ToolCall] = []
        for request_part in message.parts:
            part: Any = request_part
            kind = getattr(part, "part_kind", "")
            if kind == "text":
                texts.append(str(part.content))
            elif kind == "tool-call":
                calls.append(
                    ToolCall(
                        str(part.tool_call_id),
                        str(part.tool_name),
                        _arguments(part.args),
                    )
                )
        if texts or calls:
            converted.append(
                Message("assistant", "".join(texts), tool_calls=tuple(calls))
            )
        for native_part in message.parts:
            prompt_part: Any = native_part
            kind = getattr(prompt_part, "part_kind", "")
            if kind == "user-prompt":
                converted.append(Message("user", str(prompt_part.content)))
            elif kind == "system-prompt":
                converted.append(Message("system", str(prompt_part.content)))
            elif kind == "tool-return":
                converted.append(
                    Message(
                        "tool",
                        str(prompt_part.content),
                        tool_call_id=prompt_part.tool_call_id,
                    )
                )
    tools = tuple(
        # ToolDefinition is imported locally to keep this file test-only.
        _tool_definition(tool)
        for tool in info.function_tools
    )
    return ModelRequest(
        "fixture",
        tuple(converted),
        tools,
        max_input_tokens=input_tokens,
        max_output_tokens=output_tokens,
    )


def _tool_definition(tool: Any):
    """Convert one PydanticAI tool schema to the shared domain DTO.

    Parameters
    ----------
    tool : Any
        PydanticAI tool definition.

    Returns
    -------
    ToolDefinition
        Schema exposed to the fixture provider.
    """
    from amethyst.domain.contracts import ToolDefinition

    return ToolDefinition(
        tool.name,
        tool.description or "",
        tool.parameters_json_schema,
    )


def _arguments(value: Any) -> dict[str, Any]:
    """Normalize native tool arguments into the legacy fixture mapping.

    Parameters
    ----------
    value : Any
        Parsed or JSON-encoded tool arguments.

    Returns
    -------
    dict
        Structured call arguments.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}
