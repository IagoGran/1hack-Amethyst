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
    def definition(self) -> ToolDefinition:
        """Describe the tool name and its accepted arguments.

        Parameters
        ----------
        None

        Returns
        -------
        ToolDefinition
            Model-visible tool schema.
        """
        ...

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Execute once without retries; raise ContractError on failure.

        Parameters
        ----------
        call : ToolCall
            Tool invocation with its identifier, name, and arguments.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        ToolResult
            Bounded result with call identity and source metadata.
        """
        ...


class ConnectionTester(Protocol):
    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Return a redacted health result without exposing credentials.

        Parameters
        ----------
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        ConnectionHealth
            Value produced by the operation.
        """
        ...
