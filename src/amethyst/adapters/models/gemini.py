"""Gemini request and event translation behind the common model interface."""

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


class GeminiModelProvider(ModelAdapter):
    context_tokens = 1_000_000
    provider_name = "Gemini"
    default_endpoint = "https://generativelanguage.googleapis.com/v1beta"

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
        return {"functionDeclarations": self._tool_declarations(request)}

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
            async for event in self._events_until_deadline(
                iterator,
                deadline,
                request.idle_timeout_seconds,
                usage,
                timeout_message="Gemini request timed out.",
                idle_message="Gemini request timed out.",
            ):
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
