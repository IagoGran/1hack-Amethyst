"""Common adapter contract; application must authorize before dispatch."""

from typing import Protocol

from amethyst.domain.contracts import (
    ConnectionHealth,
    OperationContext,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


class AgentTool(Protocol):
    @property
    def definition(self) -> ToolDefinition: ...

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Execute once without retries; raise ContractError on failure."""
        ...


class ConnectionTester(Protocol):
    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Return a redacted health result without exposing credentials."""
        ...
