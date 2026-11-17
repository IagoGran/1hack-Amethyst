"""Shared chat-completion protocol for OpenAI, DeepSeek, and Ollama."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator
from typing import Any, Literal, cast

from amethyst.adapters.models._sse import stream_json
from amethyst.adapters.models.base import ModelAdapter
from amethyst.adapters.models.base import attach_usage as _attach_usage
from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    ModelCompleted,
    ModelEvent,
    ModelRequest,
    OperationContext,
    TextDelta,
    ToolCall,
    Usage,
)


class _ChatCompletionsProvider(ModelAdapter):
    provider_name = "model"
    default_endpoint = ""
    authorization = True
    line_delimited_json = False
    context_tokens = 32_000

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check provider reachability without logging credentials.

        Parameters
        ----------
        context : OperationContext
            Call scope and timeout.

        Returns
        -------
        ConnectionHealth
            Redacted connection outcome.
        """
        if self.authorization and not self._api_key:
            return ConnectionHealth(
                False,
                f"{self.provider_name} credentials are missing.",
                ErrorCode.AUTHENTICATION,
            )
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._health_request), context.timeout_seconds
            )
        except TimeoutError:
            return ConnectionHealth(
                False, f"{self.provider_name} connection timed out.", ErrorCode.TIMEOUT
            )
        except ContractError as exc:
            return ConnectionHealth(False, str(exc), exc.code)
        except (OSError, ValueError):
            return ConnectionHealth(
                False, f"{self.provider_name} is unavailable.", ErrorCode.UNAVAILABLE
            )
        return ConnectionHealth(True, f"{self.provider_name} connection is available.")

    def _health_request(self) -> None:
        """Request the provider model list using the configured credentials.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        url = self._base_url + "/models"
        headers = (
            {"Authorization": f"Bearer {self._api_key}"} if self.authorization else {}
        )
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read(64_000)
        except urllib.error.HTTPError as exc:
            code = (
                ErrorCode.AUTHENTICATION
                if exc.code in (401, 403)
                else ErrorCode.UNAVAILABLE
            )
            raise ContractError(
                code,
                f"{self.provider_name} connection failed.",
                transient=exc.code >= 500 or exc.code == 429,
            ) from None

    async def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Stream text and tool calls through the vendor-neutral model port.

        Parameters
        ----------
        request : ModelRequest
            Model ID, conversation messages, tools, and output limits.
        context : OperationContext
            Remaining call scope and timeout.

        Yields
        ------
        ModelEvent
            Text deltas followed by one completion event.

        Raises
        ------
        ContractError
            For safe provider, timeout, or tool-call parsing failures.
        """
        async for event in self._stream_chat_completions(request, context):
            yield event

    async def _stream_chat_completions(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Perform one provider stream and translate all emitted events.

        Parameters
        ----------
        request : ModelRequest
            Validated provider request.
        context : OperationContext
            Remaining call scope and timeout.

        Yields
        ------
        ModelEvent
            Translated text deltas and the final completion.
        """
        total_timeout, deadline = self._validate_stream_request(request, context)
        payload = self._payload(request)
        headers = self._request_headers()
        usage: Usage | None = None
        tool_fragments: dict[int, dict[str, str]] = {}
        final_reason: Literal["stop", "tool_calls", "length"] = "stop"
        stream = stream_json(
            self._url(request.model_id),
            headers,
            payload,
            min(total_timeout, request.idle_timeout_seconds),
            line_delimited_json=self.line_delimited_json,
        )
        iterator = stream.__aiter__()
        try:
            async for event in self._events_until_deadline(
                iterator, deadline, request.idle_timeout_seconds, usage
            ):
                parsed_text, parsed_usage, fragments, finish_reason = self._parse_event(
                    event
                )
                usage = parsed_usage if parsed_usage is not None else usage
                _merge_tool_fragments(tool_fragments, fragments)
                if parsed_text:
                    yield TextDelta(parsed_text)
                if finish_reason in ("length", "tool_calls"):
                    final_reason = cast(Literal["length", "tool_calls"], finish_reason)
            calls = _decode_tool_fragments(tool_fragments, self.provider_name, usage)
            if calls:
                final_reason = "tool_calls"
            yield ModelCompleted(usage, tuple(calls), final_reason)
        except ContractError as error:
            _attach_usage(error, usage)
            raise
        finally:
            await stream.aclose()

    def _validate_stream_request(
        self, request: ModelRequest, context: OperationContext
    ) -> tuple[float, float]:
        """Validate required request fields and calculate the absolute deadline.

        Parameters
        ----------
        request : ModelRequest
            Provider request to validate.
        context : OperationContext
            Remaining operation timeout.

        Returns
        -------
        tuple of float
            Request timeout and monotonic deadline.

        Raises
        ------
        ContractError
            If the model ID, credentials, or remaining deadline are invalid.
        """
        if not request.model_id.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
        if self.authorization and not self._api_key:
            raise ContractError(
                ErrorCode.AUTHENTICATION,
                f"{self.provider_name} credentials are missing.",
            )
        total_timeout = min(request.total_timeout_seconds, context.timeout_seconds)
        if total_timeout <= 0:
            raise ContractError(ErrorCode.TIMEOUT, "Model request deadline expired.")
        return total_timeout, time.monotonic() + total_timeout

    def _request_headers(self) -> dict[str, str]:
        """Build request headers without adding credentials to URL parameters.

        Returns
        -------
        dict[str, str]
            Authorization header when the provider requires one.

        Parameters
        ----------
        None
        """
        if not self.authorization:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        """Build the OpenAI-compatible chat completion request body.

        Parameters
        ----------
        request : ModelRequest
            Messages, tools, model ID, and generation limit.

        Returns
        -------
        dict[str, Any]
            JSON request body accepted by compatible providers.
        """
        messages = [
            {
                "role": message.role,
                "content": message.content,
                **(
                    {"tool_call_id": message.tool_call_id}
                    if message.tool_call_id
                    else {}
                ),
                **(
                    {
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments),
                                },
                            }
                            for call in message.tool_calls
                        ]
                    }
                    if message.tool_calls
                    else {}
                ),
            }
            for message in request.messages
        ]
        payload: dict = {
            "model": request.model_id,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": request.max_output_tokens,
        }
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": definition}
                for definition in self._tool_declarations(request)
            ]
        return payload

    def _url(self, model_id: str) -> str:
        """Return the chat completion endpoint for a model ID.

        Parameters
        ----------
        model_id : str
            Configured model identifier.

        Returns
        -------
        str
            Provider endpoint URL.
        """
        return self._base_url + "/chat/completions"

    def _parse_event(
        self, event: dict
    ) -> tuple[str, Usage | None, dict[int, dict[str, str]], str | None]:
        """Translate one OpenAI-compatible or Ollama stream chunk.

        Parameters
        ----------
        event : dict
            Decoded provider response chunk.

        Returns
        -------
        tuple
            Text delta, optional usage, tool-call fragments, and finish reason.
        """
        if self.line_delimited_json:
            message = event.get("message", {})
            text = str(message.get("content", ""))
            usage = None
            if "prompt_eval_count" in event or "eval_count" in event:
                usage = Usage(
                    int(event.get("prompt_eval_count", 0)),
                    int(event.get("eval_count", 0)),
                )
            ollama_fragments = {}
            for index, call in enumerate(message.get("tool_calls", [])):
                function = call.get("function", {})
                call_id = str(call.get("id", "")) or f"{self.provider_name}-{index}"
                name = str(function.get("name", ""))
                self._tool_names[call_id] = name
                ollama_fragments[index] = {
                    "id": call_id,
                    "name": name,
                    "arguments": json.dumps(function.get("arguments", {})),
                }
            return (
                text,
                usage,
                ollama_fragments,
                "tool_calls"
                if ollama_fragments
                else ("stop" if event.get("done") else None),
            )
        usage_data = event.get("usage")
        usage = None
        if isinstance(usage_data, dict) and (
            "prompt_tokens" in usage_data or "completion_tokens" in usage_data
        ):
            usage = Usage(
                int(usage_data.get("prompt_tokens", 0)),
                int(usage_data.get("completion_tokens", 0)),
            )
        choices = event.get("choices", [])
        if not choices:
            return "", usage, {}, None
        choice = choices[0]
        delta = choice.get("delta", {})
        text = delta.get("content", "") or ""
        fragments: dict[int, dict[str, str]] = {}
        for call in delta.get("tool_calls", []):
            index = int(call.get("index", 0))
            function = call.get("function", {})
            fragments[index] = {
                "id": str(call.get("id", "")),
                "name": str(function.get("name", "")),
                "arguments": str(function.get("arguments", "")),
            }
        reason = choice.get("finish_reason")
        return text, usage, fragments, reason


def _merge_tool_fragments(
    accumulated: dict[int, dict[str, str]], fragments: dict[int, dict[str, str]]
) -> None:
    """Append partial tool-call fields by their stream index.

    Parameters
    ----------
    accumulated : dict
        Mutable tool-call fragments gathered so far.
    fragments : dict
        Fragments from the current provider event.

    Returns
    -------
    None
    """
    for index, fragment in fragments.items():
        target = accumulated.setdefault(index, {"id": "", "name": "", "arguments": ""})
        for key, value in fragment.items():
            target[key] += value


def _decode_tool_fragments(
    fragments: dict[int, dict[str, str]], provider_name: str, usage: Usage | None
) -> list[ToolCall]:
    """Decode accumulated tool-call arguments into domain values.

    Parameters
    ----------
    fragments : dict
        Provider tool-call fragments indexed by their original stream position.
    provider_name : str
        Name used to generate stable fallback IDs.
    usage : Usage or None
        Usage known for the response, attached to parsing errors when available.

    Returns
    -------
    list of ToolCall
        Complete tool calls ordered by stream index.

    Raises
    ------
    ContractError
        If a tool call contains malformed or non-object arguments.
    """
    calls = []
    for index, parts in sorted(fragments.items()):
        try:
            arguments = json.loads(parts["arguments"] or "{}")
            if not isinstance(arguments, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            raise ContractError(
                ErrorCode.UNAVAILABLE,
                "Model returned invalid tool arguments.",
                usage=usage,
            ) from None
        calls.append(
            ToolCall(
                parts["id"] or f"{provider_name}-{index}",
                parts["name"],
                arguments,
            )
        )
    return calls


class OpenAIModelProvider(_ChatCompletionsProvider):
    provider_name = "OpenAI"
    default_endpoint = "https://api.openai.com/v1"
    context_tokens = 128_000


class DeepSeekModelProvider(_ChatCompletionsProvider):
    provider_name = "DeepSeek"
    default_endpoint = "https://api.deepseek.com/v1"
    context_tokens = 64_000


class OllamaModelProvider(_ChatCompletionsProvider):
    provider_name = "Ollama"
    default_endpoint = "http://127.0.0.1:11434/api"
    authorization = False
    line_delimited_json = True
    context_tokens = 32_000

    def _url(self, model_id: str) -> str:
        """Return the local Ollama chat endpoint.

        Parameters
        ----------
        model_id : str
            Configured model identifier; Ollama receives it in the request body.

        Returns
        -------
        str
            Ollama chat endpoint URL.
        """
        return self._base_url + "/chat"

    def _health_request(self) -> None:
        """Request the local Ollama model list to check service availability.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        request = urllib.request.Request(
            self._base_url.removesuffix("/api") + "/api/tags"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read(64_000)

    def _payload(self, request: ModelRequest) -> dict:
        """Build the Ollama chat request, preserving tool-call history.

        Parameters
        ----------
        request : ModelRequest
            Messages, tools, model ID, and output limit.

        Returns
        -------
        dict
            Ollama ``/api/chat`` request body.
        """
        messages: list[dict[str, object]] = []
        for message in request.messages:
            converted: dict[str, object] = {
                "role": message.role,
                "content": message.content,
            }
            if message.tool_call_id:
                name = self._tool_names.pop(message.tool_call_id, None)
                if name is not None:
                    converted["tool_name"] = name
            if message.tool_calls:
                converted["tool_calls"] = [
                    {"function": {"name": call.name, "arguments": call.arguments}}
                    for call in message.tool_calls
                ]
                for call in message.tool_calls:
                    self._tool_names[call.id] = call.name
            messages.append(converted)
        payload: dict = {
            "model": request.model_id,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": request.max_output_tokens},
        }
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": definition}
                for definition in self._tool_declarations(request)
            ]
        return payload
