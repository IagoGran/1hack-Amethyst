"""Common contract for tools that the agent can invoke."""

from typing import Protocol


class AgentTool(Protocol):
    """Minimal interface for registrable connectors and tools."""

    @property
    def name(self) -> str:
        """Stable tool identifier."""
        ...

    def execute(self, input_data: str) -> str:
        """Execute an already authorized operation and return its result."""
        ...
