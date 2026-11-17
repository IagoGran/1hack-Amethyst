"""Bind configured tools to unique names and the agent's result contract."""

import hashlib
import json
from dataclasses import replace

from amethyst.adapters.tools.base import Tool
from amethyst.configuration.catalog import CONNECTION_SPECS, ConnectionKind
from amethyst.domain.contracts import (
    Connection,
    ContractError,
    ErrorCode,
    OperationContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from amethyst.ports.tool import AgentTool


class NamedTool(Tool):
    """Give each configured connector a distinct model-visible tool name."""

    def __init__(self, tool: AgentTool, connection: Connection) -> None:
        """Bind a connector to a collision-free alias.

        Parameters
        ----------
        tool : AgentTool
            Vendor adapter.
        connection : Connection
            Persisted connector identity.

        Returns
        -------
        None
        """
        self.tool = tool
        self.spec = CONNECTION_SPECS[ConnectionKind(connection.kind)]
        suffix = hashlib.sha256(connection.id.encode()).hexdigest()[:16]
        self._definition = replace(
            tool.definition,
            name=f"{connection.kind}_{suffix}",
            description=f"{connection.id}: {tool.definition.description}",
        )

    @property
    def definition(self) -> ToolDefinition:
        """Return the cached connector alias and schema.

        Parameters
        ----------
        None

        Returns
        -------
        ToolDefinition
            Model-visible definition unique to this connection.
        """
        return self._definition

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Translate the registered alias back to the adapter's native name.

        Parameters
        ----------
        call : ToolCall
            Model-selected invocation.
        context : OperationContext
            Application limits and session scope.

        Returns
        -------
        ToolResult
            Adapter result preserving the original call identifier.
        """
        result = await self.tool.execute(
            replace(call, name=self.tool.definition.name), context
        )
        if self.spec.content_field is not None:
            records = json.loads(result.content)
            if not isinstance(records, list):
                raise ContractError(
                    ErrorCode.INVALID_INPUT, "Invalid retrieval result."
                )
            chunks = [
                {
                    **item,
                    "content": str(item.get(self.spec.content_field, "")),
                }
                for item in records
            ]
            result = replace(result, content=json.dumps({"chunks": chunks}))
        return result
