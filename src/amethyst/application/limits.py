"""Deadline, token accounting, conservative result limits, and retry rules."""

import json
from dataclasses import asdict, replace

from amethyst.application.budgets import (
    TokenBudget as TokenBudget,
)
from amethyst.application.budgets import (
    request_tokens as request_tokens,
)
from amethyst.application.budgets import (
    token_bound as token_bound,
)
from amethyst.application.timing import Deadline as Deadline
from amethyst.application.timing import retry_delay as retry_delay
from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    ToolResult,
)
from amethyst.security.sql import require_read_only_sql as require_read_only_sql
from amethyst.serialization import bounded_json_records


def bounded_result(
    result: ToolResult, limits: Limits, kind: str = "text"
) -> ToolResult:
    """Apply row, retrieval, content-byte, and source-metadata limits.

    Parameters
    ----------
    result : ToolResult
        Tool result to inspect, redact, or bound.
    limits : Limits
        Validated operational resource limits.
    kind : str
        Provider, connector, or structured-result category.

    Returns
    -------
    ToolResult
        Bounded result with call identity and source metadata.
    """
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
            metadata = {name: child for name, child in value.items() if name != key}
            prefix = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))[
                :-1
            ]
            prefix += ("," if metadata else "") + json.dumps(key) + ":["
            content, kept = bounded_json_records(
                value[key], limits.output_bytes, prefix=prefix, suffix="]}"
            )
            truncated |= kept < len(value[key])
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
