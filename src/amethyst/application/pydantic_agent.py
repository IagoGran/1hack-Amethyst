"""Run task reasoning through PydanticAI while retaining Amethyst boundaries."""

from __future__ import annotations

import json
from typing import Any

from pydantic_ai import (
    Agent,
    RequestUsage,
    RunContext,
    TextPart,
    Tool,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai import ModelRequest as AIRequest
from pydantic_ai import ModelResponse as AIResponse
from pydantic_ai.messages import ModelMessage, SystemPromptPart
from pydantic_ai.models import Model, ModelRequestParameters

from amethyst.application.state import ProviderBinding, RunningTask
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    Message,
    ToolCall,
    ToolDefinition,
    Usage,
)
from amethyst.domain.tasks import TaskStatus


class ProviderModel(Model):
    """Adapt the existing streaming provider port to PydanticAI's model API."""

    def __init__(
        self, service: Any, record: RunningTask, binding: ProviderBinding, title: str
    ) -> None:
        """Bind a task's existing provider and bounded model runner.

        Parameters
        ----------
        service : AgentService
            Owner of provider execution and task security services.
        record : RunningTask
            Current task state and conversation.
        binding : ProviderBinding
            Configured model provider and model identifier.
        title : str
            Retained conversation title.

        Returns
        -------
        None
        """
        super().__init__()
        self.service = service
        self.record = record
        self.binding = binding
        self.title = title

    @property
    def model_name(self) -> str:
        """Return the configured public model identifier.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Configured model identifier.
        """
        return self.binding.model_id

    @property
    def system(self) -> str:
        """Identify PydanticAI as the owner of tool orchestration.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Framework identifier.
        """
        return "pydantic-ai"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: Any,
        model_request_parameters: ModelRequestParameters,
    ) -> AIResponse:
        """Generate one bounded response using the configured provider port.

        Parameters
        ----------
        messages : list[ModelMessage]
            PydanticAI request and response history for this run.
        model_settings : Any
            PydanticAI-specific settings, unused because Amethyst limits apply.
        model_request_parameters : ModelRequestParameters
            Registered PydanticAI tools and output constraints.

        Returns
        -------
        ModelResponse
            Provider text or tool calls translated to PydanticAI parts.
        """
        self.record.messages = from_ai_messages(messages)
        instructions = _request_instructions(messages)
        text, completed = await self.service._model_runner.generate(
            self.record, self.binding, instructions
        )
        if completed.tool_calls and not text.strip():
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "A visible plan is required before tool execution.",
            )
        self.record.messages.append(
            Message("assistant", text, tool_calls=completed.tool_calls)
        )
        self.record.partial_text = ""
        await self.service._save(self.record, self.title)
        parts: list[Any] = []
        if text:
            parts.append(TextPart(text))
        parts.extend(
            ToolCallPart(
                tool_name=call.name,
                args=call.arguments,
                tool_call_id=call.id,
            )
            for call in completed.tool_calls
        )
        usage = completed.usage or Usage()
        return AIResponse(
            parts=parts,
            usage=RequestUsage(
                input_tokens=usage.input_tokens, output_tokens=usage.output_tokens
            ),
            model_name=self.model_name,
        )


def to_ai_messages(messages: list[Message]) -> list[ModelMessage]:
    """Convert retained Amethyst history into PydanticAI conversation messages.

    Parameters
    ----------
    messages : list[Message]
        Prior conversation messages, excluding the current user prompt.

    Returns
    -------
    list[ModelMessage]
        PydanticAI-compatible history preserving tool call identifiers.
    """
    converted: list[ModelMessage] = []
    tool_names: dict[str, str] = {}
    for message in messages:
        if message.role == "user":
            converted.append(AIRequest([UserPromptPart(message.content)]))
        elif message.role == "system":
            converted.append(AIRequest([SystemPromptPart(message.content)]))
        elif message.role == "assistant":
            parts: list[Any] = [TextPart(message.content)] if message.content else []
            for call in message.tool_calls:
                tool_names[call.id] = call.name
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
            name = tool_names.get(message.tool_call_id, "unknown")
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


def from_ai_messages(messages: list[ModelMessage]) -> list[Message]:
    """Convert PydanticAI request history into Amethyst's retained format.

    Parameters
    ----------
    messages : list[ModelMessage]
        PydanticAI message history after a partial or complete run.

    Returns
    -------
    list[Message]
        Amethyst conversation messages preserving calls and results.
    """
    converted: list[Message] = []
    for message in messages:
        if isinstance(message, AIRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    converted.append(Message("user", _text_content(part.content)))
                elif isinstance(part, ToolReturnPart):
                    converted.append(
                        Message("tool", _text_content(part.content), part.tool_call_id)
                    )
        elif isinstance(message, AIResponse):
            texts = [
                part.content for part in message.parts if isinstance(part, TextPart)
            ]
            calls = tuple(
                ToolCall(
                    part.tool_call_id,
                    part.tool_name,
                    _call_arguments(part.args),
                )
                for part in message.parts
                if isinstance(part, ToolCallPart)
            )
            if texts or calls:
                converted.append(Message("assistant", "".join(texts), tool_calls=calls))
    return converted


def _text_content(content: Any) -> str:
    """Make textual tool and user content fit the retained string contract.

    Parameters
    ----------
    content : Any
        PydanticAI content value.

    Returns
    -------
    str
        Text or bounded JSON representation.
    """
    return content if isinstance(content, str) else json.dumps(content, default=str)


def _request_instructions(messages: list[ModelMessage]) -> str:
    """Read the current system instructions from PydanticAI request history.

    Parameters
    ----------
    messages : list[ModelMessage]
        PydanticAI message history for the current run.

    Returns
    -------
    str
        Latest explicit instruction text or an empty string.
    """
    for message in reversed(messages):
        if isinstance(message, AIRequest) and message.instructions:
            return message.instructions
        if isinstance(message, AIRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    return part.content
    return ""


def _call_arguments(arguments: str | dict[str, Any] | None) -> dict[str, Any]:
    """Normalize PydanticAI tool arguments into the shared call contract.

    Parameters
    ----------
    arguments : str, dict, or None
        Parsed or JSON-encoded tool arguments.

    Returns
    -------
    dict[str, Any]
        Object arguments, or an empty object for invalid input.
    """
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def build_tools(service: Any, record: RunningTask, title: str) -> list[Tool[Any]]:
    """Create PydanticAI function tools backed by the trusted dispatcher.

    Parameters
    ----------
    service : AgentService
        Task orchestrator and protected tool dispatcher owner.
    record : RunningTask
        Task receiving tool outputs and status events.
    title : str
        Retained conversation title.

    Returns
    -------
    list[Tool[Any]]
        PydanticAI tool functions for all currently enabled operations.
    """
    tools: list[Tool[Any]] = []
    for definition in service._tool_dispatcher.definitions():
        tools.append(_build_tool(service, record, definition, title))
    return tools


def _build_tool(
    service: Any, record: RunningTask, definition: ToolDefinition, title: str
) -> Tool[Any]:
    """Wrap one dispatcher operation as a PydanticAI schema-driven tool.

    Parameters
    ----------
    service : AgentService
        Task orchestrator that enforces permissions and approvals.
    record : RunningTask
        Task receiving the operation result.
    definition : ToolDefinition
        Stable name, description, and JSON argument schema.
    title : str
        Retained conversation title.

    Returns
    -------
    Tool
        PydanticAI tool that delegates execution to ToolDispatcher.
    """

    async def invoke(ctx: RunContext[None], **arguments: Any) -> str:
        """Execute one named operation through Amethyst authorization.

        Parameters
        ----------
        ctx : RunContext[None]
            PydanticAI call context with the model-generated call identifier.
        **arguments : Any
            Model-provided arguments validated again by the dispatcher/adapter.

        Returns
        -------
        str
            Tool result passed back to PydanticAI for the next reasoning step.
        """
        if not ctx.tool_call_id:
            raise ContractError(ErrorCode.INVALID_INPUT, "Tool call ID is missing.")
        call = ToolCall(ctx.tool_call_id, definition.name, arguments)
        result = await service._tool_dispatcher.execute(record, call)
        await service._emit(record, result)
        record.messages.append(Message("tool", result.content, call.id))
        await service._save(record, title)
        await service._state(
            record,
            TaskStatus.RUNNING,
            "Inspecting tool results and validating the outcome.",
        )
        return str(result.content)

    return Tool.from_schema(
        invoke,
        name=definition.name,
        description=definition.description,
        json_schema=definition.input_schema,
        takes_ctx=True,
        sequential=True,
    )


async def run_agent(
    service: Any,
    record: RunningTask,
    binding: ProviderBinding,
    instructions: str,
    title: str,
) -> None:
    """Let PydanticAI drive reasoning and tool execution until final output.

    Parameters
    ----------
    service : AgentService
        Session orchestrator and existing provider/security owner.
    record : RunningTask
        Task and conversation being advanced.
    binding : ProviderBinding
        Configured model provider and model identifier.
    instructions : str
        System and selected skill instructions.
    title : str
        Retained conversation title.

    Returns
    -------
    None
    """
    model = ProviderModel(service, record, binding, title)
    pydantic_agent = Agent(
        model,
        instructions=instructions,
        tools=build_tools(service, record, title),
        retries=0,
        name="amethyst-agent",
    )
    previous = record.messages[:-1]
    result = await pydantic_agent.run(
        record.task.request, message_history=to_ai_messages(previous)
    )
    record.messages = from_ai_messages(result.all_messages())
    record.partial_text = ""
    await service._save(record, title)
