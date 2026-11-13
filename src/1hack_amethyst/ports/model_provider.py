"""Provider-independent contract for generating model responses."""

from typing import Protocol


class ModelProvider(Protocol):
    """Minimal interface implemented by model adapters."""

    def complete(self, prompt: str) -> str:
        """Generate a response for a prompt."""
        ...
