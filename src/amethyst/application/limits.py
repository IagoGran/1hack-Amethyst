"""Deadline, token accounting, conservative result limits, and retry rules."""

import asyncio
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, replace

from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    ModelRequest,
    ToolResult,
    Usage,
)


def token_bound(text: str) -> int:
    """UTF-8 byte upper bound; conservative until C supplies model tokenizers."""
    return len(text.encode("utf-8"))


def request_tokens(request: ModelRequest) -> int:
    return (
        token_bound(
            json.dumps(
                {
                    "messages": [asdict(m) for m in request.messages],
                    "tools": [asdict(t) for t in request.tools],
                },
                ensure_ascii=False,
            )
        )
        + 128
    )


class Deadline:
    def __init__(
        self, seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.clock = clock
        self.end = clock() + seconds

    def remaining(self) -> float:
        remaining = self.end - self.clock()
        if remaining <= 0:
            raise ContractError(ErrorCode.TIMEOUT, "Task deadline exceeded.")
        return remaining

    async def run[T](self, operation: Callable[[], Awaitable[T]], limit: float) -> T:
        try:
            async with asyncio.timeout(min(limit, self.remaining())):
                return await operation()
        except TimeoutError:
            raise ContractError(ErrorCode.TIMEOUT, "Operation timed out.") from None

    async def approval_wait[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        self.remaining()
        start = self.clock()
        try:
            return await operation()
        finally:
            self.end += self.clock() - start


class TokenBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def can_reserve(self, tokens: int) -> bool:
        return self.used + tokens <= self.limit

    def charge(self, usage: Usage | None, reserved: int) -> Usage:
        if usage is None:
            usage = Usage(reserved, 0)
        if usage.input_tokens < 0 or usage.output_tokens < 0:
            self.used += reserved
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Provider returned invalid usage."
            )
        self.used += usage.input_tokens + usage.output_tokens
        return usage

    def increase(self, tokens: int) -> None:
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Budget increase must be a positive integer."
            )
        self.limit += tokens


def retry_delay(
    error: ContractError, attempt: int, retries: int, *, safe: bool
) -> float | None:
    if (
        not safe
        or attempt >= retries
        or not error.transient
        or error.code not in {ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT}
    ):
        return None
    return float(
        max(2**attempt + random.uniform(0, 0.25), error.retry_after_seconds or 0)
    )


def bounded_result(
    result: ToolResult, limits: Limits, kind: str = "text"
) -> ToolResult:
    content = result.content
    truncated = result.truncated
    if kind in {"sql", "retrieval"}:
        try:
            value = json.loads(content)
            key = "rows" if kind == "sql" else "chunks"
            items = value[key]
            if not isinstance(value, dict) or not isinstance(items, list):
                raise ValueError
            maximum = limits.sql_rows if kind == "sql" else limits.retrieval_chunks
            truncated |= len(items) > maximum
            value[key] = items[:maximum]
            if kind == "retrieval":
                for chunk in value[key]:
                    if not isinstance(chunk, dict) or not isinstance(
                        chunk.get("content"), str
                    ):
                        raise ValueError
                    raw = chunk["content"].encode()
                    if len(raw) > limits.chunk_tokens:
                        chunk["content"] = raw[: limits.chunk_tokens].decode(
                            errors="ignore"
                        )
                        truncated = True
            content = json.dumps(value, ensure_ascii=False)
            # Preserve valid structured results while reducing byte size.
            while len(content.encode()) > limits.output_bytes and value[key]:
                value[key].pop()
                truncated = True
                content = json.dumps(value, ensure_ascii=False)
        except (ValueError, KeyError, TypeError):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Malformed structured tool result."
            ) from None
    raw = content.encode()
    if len(raw) > limits.output_bytes:
        if kind in {"sql", "retrieval"}:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Tool metadata exceeds the output limit."
            )
        content = raw[: limits.output_bytes].decode(errors="ignore")
        truncated = True
    # Attribution also consumes the output budget; unbounded metadata is rejected.
    sources_bytes = len(json.dumps([asdict(s) for s in result.sources]).encode())
    if result.sources and sources_bytes + len(content.encode()) > limits.output_bytes:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Tool sources exceed the output limit."
        )
    return replace(result, content=content, truncated=truncated)


def require_read_only_sql(query: str) -> None:
    """Conservative admission policy, in addition to C's DB read-only transaction.

    Comments, quoted identifiers and literals are removed before token inspection.
    Unknown/unsafe statements are denied. DB permissions remain mandatory because
    SELECT functions can have side effects and dialects differ.
    """
    stripped = re.sub(
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/", " ", query, flags=re.S
    )
    tokens = re.findall(r"[a-z_]+|;", stripped.lower())
    forbidden = {
        "insert",
        "update",
        "delete",
        "merge",
        "replace",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "copy",
        "call",
        "execute",
        "pragma",
        "attach",
        "detach",
        "vacuum",
        "into",
        "lock",
        "load",
        "pg_sleep",
        "dblink",
        "lo_export",
        "lo_import",
    }
    if (
        not tokens
        or tokens[0] not in {"select", "with"}
        or any(t in forbidden for t in tokens)
        or ";" in tokens[:-1]
        or "$" in stripped
    ):
        raise ContractError(
            ErrorCode.PERMISSION_DENIED, "Only read-only SQL queries are permitted."
        )
