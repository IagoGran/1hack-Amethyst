"""Asynchronous, vendor-neutral model boundary."""

from collections.abc import AsyncIterator
from typing import Protocol

from amethyst.domain.contracts import (
    ModelCapabilities,
    ModelEvent,
    ModelRequest,
    OperationContext,
)


class ModelProvider(Protocol):
    async def capabilities(self, model_id: str) -> ModelCapabilities: ...

    def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Yield deltas and one completion; non-streaming adapters yield one delta.

        Raise ContractError for safe failures; propagate asyncio cancellation.
        Include consumed usage in ContractError when available. Never retry here.
        """
        ...
