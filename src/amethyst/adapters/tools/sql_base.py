"""Shared SQL tool admission, schema, result formatting, and attribution."""

import json
from abc import abstractmethod
from typing import Any

from amethyst.adapters.tools.base import Tool
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    OperationContext,
    Source,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from amethyst.serialization import bounded_json_records


class ReadOnlySQLTool(Tool):
    """Share SQL behavior while databases retain their enforcement and drivers."""

    name: str
    database_label: str
    connection_id: str

    @property
    def definition(self) -> ToolDefinition:
        """Describe the common single-query read-only SQL interface.

        Parameters
        ----------
        None

        Returns
        -------
        ToolDefinition
            Database-specific name with a shared query schema.
        """
        return ToolDefinition(
            self.name,
            f"Run one read-only SQL query against the configured "
            f"{self.database_label} database.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            read_only=True,
        )

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Validate the query and preserve common bounds and database attribution.

        Parameters
        ----------
        call : ToolCall
            SQL invocation with a query string.
        context : OperationContext
            Deadline and output-byte limit.

        Returns
        -------
        ToolResult
            Bounded SQL rows and columns with the connector's source identifier.
        """
        query = call.arguments.get("query")
        if call.name != self.name or not isinstance(query, str) or not query.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A SQL query is required.")
        rows, columns, truncated = await self._execute_query(query, context)
        content, byte_truncated = _format_result(
            rows, columns, max(0, context.output_limit_bytes)
        )
        return ToolResult(
            call.id, content, (Source(self.connection_id),), truncated or byte_truncated
        )

    @abstractmethod
    async def _execute_query(
        self, query: str, context: OperationContext
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Execute through database-specific timeouts and enforced read-only access.

        Parameters
        ----------
        query : str
            Validated nonempty query.
        context : OperationContext
            Operation timeout and output limits.

        Returns
        -------
        tuple
            Rows, column names, and row-limit truncation state.
        """
        raise NotImplementedError


def _format_result(
    rows: list[dict[str, Any]], columns: list[str], limit: int
) -> tuple[str, bool]:
    """Serialize SQL metadata and rows within the output-byte limit.

    Parameters
    ----------
    rows : list of dict
        Result rows. The input list is not modified.
    columns : list of str
        Result column names.
    limit : int
        Maximum encoded output size.

    Returns
    -------
    tuple
        Bounded JSON object and truncation indicator.
    """
    metadata = json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
    prefix = '{"columns":' + metadata + ',"rows":['
    try:
        payload, kept = bounded_json_records(rows, limit, prefix=prefix, suffix="]}")
    except ValueError:
        return ("{}" if limit >= 2 else ""), True
    return payload, kept < len(rows)
