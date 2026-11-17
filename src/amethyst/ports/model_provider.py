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
    async def capabilities(self, model_id: str) -> ModelCapabilities:
        """Report the configured model capabilities and context capacity.

        Parameters
        ----------
        model_id : str
            Configured model identifier.

        Returns
        -------
        ModelCapabilities
            Supported generation features and context capacity.
        """
        ...

    def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Yield deltas and one completion; non-streaming adapters yield one delta.

        Raise ContractError for safe failures; propagate asyncio cancellation.
        Include consumed usage in ContractError when available. Never retry here.

        Parameters
        ----------
        request : ModelRequest
            Typed request describing the operation and its scope.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        AsyncIterator[ModelEvent]
            Value produced by the operation.
        """
        ...
