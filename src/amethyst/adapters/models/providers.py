"""OpenAI, Gemini, DeepSeek, and Ollama adapters for the shared model port."""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal, cast
from urllib.parse import quote

from amethyst.adapters.models._sse import stream_json
from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    ModelCapabilities,
    ModelCompleted,
    ModelEvent,
    ModelRequest,
    OperationContext,
    TextDelta,
    ToolCall,
    Usage,
)


class _ChatCompletionsProvider:
    provider_name = "model"
    default_endpoint = ""
    authorization = True
    line_delimited_json = False
    context_tokens = 32_000

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str | None = None,
        context_tokens: int | None = None,
    ) -> None:
        """Configure an OpenAI-compatible model endpoint.

        Parameters
        ----------
        api_key : str, optional
            Secret resolved from the credential service.
        base_url : str or None, optional
            Provider API root. Uses the provider default when omitted.
        context_tokens : int or None, optional
            Configured context capacity; otherwise uses the provider default.
        """
        self._api_key = api_key
        self._base_url = (base_url or self.default_endpoint).rstrip("/")
        self._context_tokens = context_tokens or self.context_tokens
        self._tool_names: dict[str, str] = {}

    async def capabilities(self, model_id: str) -> ModelCapabilities:
        """Report streaming, tool-call, and context-window capabilities.

        Parameters
        ----------
        model_id : str
            Configured model identifier.

        Returns
        -------
        ModelCapabilities
            Capabilities exposed through the shared model port.

        Raises
        ------
        ContractError
            If no model identifier was supplied.
        """
        if not model_id.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
        return ModelCapabilities(
            streaming=True, tool_calls=True, context_tokens=self._context_tokens
        )

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
        """Request the provider model list using the configured credentials."""
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
        """
        if not self.authorization:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _events_until_deadline(
        self,
        iterator: AsyncIterator[dict[str, Any]],
        deadline: float,
        idle_timeout: float,
        usage: Usage | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield provider chunks while enforcing idle and total deadlines.

        Parameters
        ----------
        iterator : AsyncIterator
            Provider event stream.
        deadline : float
            Absolute monotonic deadline.
        idle_timeout : float
            Maximum wait for one event.
        usage : Usage or None
            Usage known before this request.

        Yields
        ------
        dict
            Raw decoded provider events.

        Raises
        ------
        ContractError
            If the total or idle timeout expires.
        """
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ContractError(
                    ErrorCode.TIMEOUT,
                    "Model request timed out.",
                    transient=True,
                    usage=usage,
                )
            try:
                yield await asyncio.wait_for(
                    iterator.__anext__(), timeout=min(remaining, idle_timeout)
                )
            except StopAsyncIteration:
                return
            except TimeoutError:
                raise ContractError(
                    ErrorCode.TIMEOUT,
                    "Model request stopped making progress.",
                    transient=True,
                    usage=usage,
                ) from None

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
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in request.tools
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


def _attach_usage(error: ContractError, usage: Usage | None) -> None:
    """Attach observed usage to a contract error when the error lacks it.

    Parameters
    ----------
    error : ContractError
        Provider error to update.
    usage : Usage or None
        Usage observed before the failure.
    """
    if error.usage is None and usage is not None:
        error.usage = usage


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
        """Request the local Ollama model list to check service availability."""
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
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in request.tools
            ]
        return payload


class GeminiModelProvider:
    provider_name = "Gemini"
    default_endpoint = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str | None = None,
        context_tokens: int = 1_000_000,
    ) -> None:
        """Configure Gemini credentials, API root, and context capacity.

        Parameters
        ----------
        api_key : str, optional
            Secret resolved through the credential service.
        base_url : str or None, optional
            Gemini API root. Uses the provider default when omitted.
        context_tokens : int, optional
            Configured model context capacity.
        """
        self._api_key = api_key
        self._base_url = (base_url or self.default_endpoint).rstrip("/")
        self._context_tokens = context_tokens
        self._tool_names: dict[str, str] = {}

    async def capabilities(self, model_id: str) -> ModelCapabilities:
        """Report Gemini streaming and function-call capabilities.

        Parameters
        ----------
        model_id : str
            Configured model identifier.

        Returns
        -------
        ModelCapabilities
            Gemini capabilities with the configured context capacity.

        Raises
        ------
        ContractError
            If ``model_id`` is empty.
        """
        if not model_id.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
        return ModelCapabilities(True, True, self._context_tokens)

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check Gemini API reachability using the configured credential.

        Parameters
        ----------
        context : OperationContext
            Operation timeout and call scope.

        Returns
        -------
        ConnectionHealth
            Redacted health outcome.
        """
        if not self._api_key:
            return ConnectionHealth(
                False, "Gemini credentials are missing.", ErrorCode.AUTHENTICATION
            )
        url = f"{self._base_url}/models?key={quote(self._api_key, safe='')}"
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_get_json, url), context.timeout_seconds
            )
        except TimeoutError:
            return ConnectionHealth(
                False, "Gemini connection timed out.", ErrorCode.TIMEOUT
            )
        except ContractError as exc:
            return ConnectionHealth(False, str(exc), exc.code)
        except (OSError, ValueError):
            return ConnectionHealth(
                False, "Gemini is unavailable.", ErrorCode.UNAVAILABLE
            )
        return ConnectionHealth(True, "Gemini connection is available.")

    async def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Stream Gemini text, function calls, usage, and completion.

        Parameters
        ----------
        request : ModelRequest
            Messages, tools, model ID, and output limit.
        context : OperationContext
            Remaining operation deadline.

        Yields
        ------
        ModelEvent
            Text deltas followed by one completion event.

        Raises
        ------
        ContractError
            If credentials, request data, or the provider response are invalid.
        """
        if not request.model_id.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
        if not self._api_key:
            raise ContractError(
                ErrorCode.AUTHENTICATION, "Gemini credentials are missing."
            )
        url, payload = self._build_gemini_request(request)
        async for event in self._stream_gemini(url, payload, request, context):
            yield event

    def _build_gemini_request(
        self, request: ModelRequest
    ) -> tuple[str, dict[str, Any]]:
        """Translate shared messages and tools into a Gemini request.

        Parameters
        ----------
        request : ModelRequest
            Provider-neutral request.

        Returns
        -------
        tuple
            Gemini endpoint URL and JSON request body.

        Raises
        ------
        ContractError
            If a tool response does not match a recorded function call.
        """
        contents, system_parts = self._gemini_contents(request)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": request.max_output_tokens},
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if request.tools:
            payload["tools"] = [self._function_declarations(request)]
        model = quote(request.model_id, safe="")
        api_key = quote(self._api_key, safe="")
        url = (
            f"{self._base_url}/models/{model}:streamGenerateContent"
            f"?alt=sse&key={api_key}"
        )
        return url, payload

    def _gemini_contents(
        self, request: ModelRequest
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Convert domain messages into Gemini content and system parts.

        Parameters
        ----------
        request : ModelRequest
            Provider-neutral messages.

        Returns
        -------
        tuple
            Conversation contents and system instruction parts.

        Raises
        ------
        ContractError
            If a tool result has no matching preceding function call.
        """
        contents: list[dict[str, object]] = []
        system_parts: list[dict[str, object]] = []
        for message in request.messages:
            if message.role == "system":
                system_parts.append({"text": message.content})
            elif message.role == "tool":
                name = self._tool_names.pop(message.tool_call_id or "", None)
                if name is None:
                    raise ContractError(
                        ErrorCode.INVALID_INPUT,
                        "Gemini tool response has no matching call.",
                    )
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": name,
                                    "response": {"content": message.content},
                                }
                            }
                        ],
                    }
                )
            else:
                parts: list[dict[str, object]] = (
                    [{"text": message.content}] if message.content else []
                )
                for call in message.tool_calls:
                    self._tool_names[call.id] = call.name
                    parts.append(
                        {"functionCall": {"name": call.name, "args": call.arguments}}
                    )
                contents.append(
                    {
                        "role": "model" if message.role == "assistant" else "user",
                        "parts": parts,
                    }
                )
        return contents, system_parts

    def _function_declarations(self, request: ModelRequest) -> dict[str, Any]:
        """Build the Gemini function declaration envelope.

        Parameters
        ----------
        request : ModelRequest
            Request containing tool definitions.

        Returns
        -------
        dict
            Gemini tools entry containing function declarations.
        """
        return {
            "functionDeclarations": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                }
                for tool in request.tools
            ]
        }

    async def _stream_gemini(
        self,
        url: str,
        payload: dict[str, Any],
        request: ModelRequest,
        context: OperationContext,
    ) -> AsyncIterator[ModelEvent]:
        """Consume Gemini response chunks within idle and total deadlines.

        Parameters
        ----------
        url : str
            Gemini streaming endpoint.
        payload : dict
            Gemini request body.
        request : ModelRequest
            Shared request providing timeout values.
        context : OperationContext
            Remaining operation deadline.

        Yields
        ------
        ModelEvent
            Text deltas and one final completion event.
        """
        total_timeout = min(request.total_timeout_seconds, context.timeout_seconds)
        if total_timeout <= 0:
            raise ContractError(ErrorCode.TIMEOUT, "Gemini request deadline expired.")
        deadline = time.monotonic() + total_timeout
        usage: Usage | None = None
        calls: list[ToolCall] = []
        stream = stream_json(
            url, {}, payload, min(total_timeout, request.idle_timeout_seconds)
        )
        iterator = stream.__aiter__()
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ContractError(
                        ErrorCode.TIMEOUT,
                        "Gemini request timed out.",
                        transient=True,
                        usage=usage,
                    )
                try:
                    event = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=min(request.idle_timeout_seconds, remaining),
                    )
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise ContractError(
                        ErrorCode.TIMEOUT,
                        "Gemini request timed out.",
                        transient=True,
                        usage=usage,
                    ) from None
                text, new_calls, event_usage = self._parse_gemini_event(event)
                if text:
                    yield TextDelta(text)
                calls.extend(new_calls)
                usage = event_usage if event_usage is not None else usage
            finish_reason: Literal["stop", "tool_calls"] = (
                "tool_calls" if calls else "stop"
            )
            yield ModelCompleted(usage, tuple(calls), finish_reason)
        except ContractError as error:
            _attach_usage(error, usage)
            raise
        finally:
            await stream.aclose()

    def _parse_gemini_event(
        self, event: dict[str, Any]
    ) -> tuple[str, list[ToolCall], Usage | None]:
        """Translate one Gemini response chunk into domain values.

        Parameters
        ----------
        event : dict
            Decoded Gemini response event.

        Returns
        -------
        tuple
            Concatenated text, tool calls, and usage when reported.
        """
        text_parts = []
        calls = []
        for candidate in event.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                if isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
                function = part.get("functionCall")
                if isinstance(function, dict):
                    call_id = f"gemini-{uuid.uuid4().hex}"
                    name = str(function.get("name", ""))
                    self._tool_names[call_id] = name
                    calls.append(ToolCall(call_id, name, function.get("args", {})))
        metadata = event.get("usageMetadata", {})
        usage = None
        if "promptTokenCount" in metadata or "candidatesTokenCount" in metadata:
            usage = Usage(
                int(metadata.get("promptTokenCount", 0)),
                int(metadata.get("candidatesTokenCount", 0)),
            )
        return "".join(text_parts), calls, usage


def _get_json(url: str) -> dict[str, Any]:
    """Fetch a JSON document without exposing URL or credential details.

    Parameters
    ----------
    url : str
        Provider metadata endpoint.

    Returns
    -------
    dict
        Decoded JSON object.

    Raises
    ------
    ContractError
        For HTTP failures using a redacted provider message.
    json.JSONDecodeError
        If the provider does not return a JSON object.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read(256_000))
            if not isinstance(payload, dict):
                raise json.JSONDecodeError("Expected JSON object", "", 0)
            return cast(dict[str, Any], payload)
    except urllib.error.HTTPError as exc:
        code = (
            ErrorCode.AUTHENTICATION
            if exc.code in (401, 403)
            else ErrorCode.UNAVAILABLE
        )
        raise ContractError(
            code,
            "Gemini connection failed.",
            transient=exc.code >= 500 or exc.code == 429,
        ) from None
