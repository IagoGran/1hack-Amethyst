"""Brave Search API connector with bounded results and source URLs."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, cast

from amethyst.adapters.http import retry_after as _retry_after
from amethyst.adapters.tools.base import Tool
from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    OperationContext,
    Source,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


class BraveSearchTool(Tool):
    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.search.brave.com/res/v1/web/search",
        max_results: int = 8,
    ) -> None:
        """Configure Brave credentials and result limits.

        Parameters
        ----------
        api_key : str
            Secret loaded from the credential service.
        endpoint : str, optional
            Brave Search API endpoint.
        max_results : int, optional
            Maximum result count exposed to tool calls.

        Returns
        -------
        None
        """
        self._api_key = api_key
        self._endpoint = endpoint
        self._max_results = min(max(1, max_results), 20)

    @property
    def definition(self) -> ToolDefinition:
        """Describe the web search tool and its accepted arguments.

        Returns
        -------
        ToolDefinition
            Search query schema.

        Parameters
        ----------
        None
        """
        return ToolDefinition(
            "web.brave.search",
            "Search Brave and return result titles, descriptions, and URLs.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["query"],
            },
        )

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Search the web and return bounded results with source references.

        Parameters
        ----------
        call : ToolCall
            Search query and optional count.
        context : OperationContext
            Request timeout and output-byte limit.

        Returns
        -------
        ToolResult
            Search results and corresponding HTTP sources.

        Raises
        ------
        ContractError
            For invalid input, timeout, authentication, or provider failures.
        """
        query = call.arguments.get("query")
        if (
            call.name != self.definition.name
            or not isinstance(query, str)
            or not query.strip()
        ):
            raise ContractError(ErrorCode.INVALID_INPUT, "A search query is required.")
        count = call.arguments.get("count", self._max_results)
        if not isinstance(count, int) or isinstance(count, bool):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Search result count must be an integer."
            )
        count = min(max(count, 1), self._max_results)
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(self._request, query, count, context.timeout_seconds),
                timeout=max(0.01, context.timeout_seconds),
            )
        except TimeoutError:
            raise ContractError(
                ErrorCode.TIMEOUT, "Brave Search timed out.", transient=True
            ) from None
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ContractError(
                    ErrorCode.AUTHENTICATION, "Brave Search authentication failed."
                ) from None
            raise ContractError(
                ErrorCode.UNAVAILABLE,
                "Brave Search is unavailable.",
                transient=exc.code >= 500 or exc.code == 429,
                retry_after_seconds=_retry_after(exc.headers.get("Retry-After")),
            ) from None
        except (OSError, json.JSONDecodeError):
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Brave Search is unavailable.", transient=True
            ) from None

        return self._result(payload, call.id, count, context.output_limit_bytes)

    def _result(
        self, payload: dict[str, Any], call_id: str, count: int, output_limit: int
    ) -> ToolResult:
        """Convert a Brave response into a bounded domain result.

        Parameters
        ----------
        payload : dict
            Decoded Brave response object.
        call_id : str
            ID of the originating tool call.
        count : int
            Maximum number of results requested.
        output_limit : int
            Maximum serialized output size.

        Returns
        -------
        ToolResult
            Valid JSON result with matching source references.

        Raises
        ------
        ContractError
            If the response structure is invalid.
        """
        web_results = payload.get("web", {})
        if not isinstance(web_results, dict):
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Brave Search returned invalid data."
            )
        results = web_results.get("results", [])
        if not isinstance(results, list):
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Brave Search returned invalid data."
            )
        items = []
        sources = []
        truncated = len(results) > count
        for item in results[:count]:
            url = str(item.get("url", ""))
            if not url.startswith(("https://", "http://")):
                continue
            title = str(item.get("title", ""))
            description = str(item.get("description", ""))
            items.append({"title": title, "description": description, "url": url})
            sources.append(Source(identifier=url, title=title, url=url))
        return self._records_result(
            call_id, items, sources, output_limit, truncated=truncated
        )

    def _request(self, query: str, count: int, timeout: float) -> dict[str, Any]:
        """Call Brave Search and decode its JSON response.

        Parameters
        ----------
        query : str
            User search terms.
        count : int
            Maximum number of results requested.
        timeout : float
            Network request timeout in seconds.

        Returns
        -------
        dict
            Decoded Brave response object.

        Raises
        ------
        OSError
            If the request fails.
        json.JSONDecodeError
            If the response is not a JSON object.
        """
        url = (
            self._endpoint + "?" + urllib.parse.urlencode({"q": query, "count": count})
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self._api_key,
            },
        )
        with urllib.request.urlopen(request, timeout=max(0.1, timeout)) as response:
            payload = json.loads(response.read(2_000_000))
            if not isinstance(payload, dict):
                raise json.JSONDecodeError("Expected JSON object", "", 0)
            return cast(dict[str, Any], payload)

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check Brave Search access using a minimal request.

        Parameters
        ----------
        context : OperationContext
            Connection-test timeout.

        Returns
        -------
        ConnectionHealth
            Redacted availability or failure result.
        """
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self._request, "amethyst health check", 1, context.timeout_seconds
                ),
                timeout=max(0.01, context.timeout_seconds),
            )
        except urllib.error.HTTPError as exc:
            code = (
                ErrorCode.AUTHENTICATION
                if exc.code in (401, 403)
                else ErrorCode.UNAVAILABLE
            )
            return ConnectionHealth(False, "Brave Search connection failed.", code)
        except TimeoutError:
            return ConnectionHealth(
                False, "Brave Search connection timed out.", ErrorCode.TIMEOUT
            )
        except (OSError, ValueError):
            return ConnectionHealth(
                False, "Brave Search is unavailable.", ErrorCode.UNAVAILABLE
            )
        return ConnectionHealth(True, "Brave Search connection is available.")
