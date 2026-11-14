"""Shared provider setup; model generation stays independent of resource tools."""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    ModelCapabilities,
    ModelEvent,
    ModelRequest,
    OperationContext,
    Usage,
)


class ModelAdapter(ABC):
    """Share provider setup and capacity discovery across model protocols."""

    default_endpoint = ""
    context_tokens = 32_000

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str | None = None,
        context_tokens: int | None = None,
    ) -> None:
        """Configure provider credentials, endpoint, and context capacity.

        Parameters
        ----------
        api_key : str, optional
            Secret resolved from the credential service.
        base_url : str or None, optional
            Provider API root. Uses the provider default when omitted.
        context_tokens : int or None, optional
            Configured context capacity; otherwise uses the provider default.

        Returns
        -------
        None
        """
        self._api_key = api_key
        self._base_url = (base_url or self.default_endpoint).rstrip("/")
        self._context_tokens = context_tokens or self.context_tokens
        self._tool_names: dict[str, str] = {}

    async def capabilities(self, model_id: str) -> ModelCapabilities:
        """Report streaming, tool-call, and context-window capabilities.

        Parameters
        ----------
        model_id : str
            Configured model identifier.

        Returns
        -------
        ModelCapabilities
            Capabilities exposed through the shared model port.

        Raises
        ------
        ContractError
            If no model identifier was supplied.
        """
        if not model_id.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
        return ModelCapabilities(
            streaming=True, tool_calls=True, context_tokens=self._context_tokens
        )

    @abstractmethod
    def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Generate model events without executing requested tools.

        Parameters
        ----------
        request : ModelRequest
            Conversation and available tool schemas.
        context : OperationContext
            Operation scope and deadline.

        Returns
        -------
        AsyncIterator of ModelEvent
            Text, requested calls, and completion usage.
        """
        raise NotImplementedError

    @abstractmethod
    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check provider availability with redacted feedback.

        Parameters
        ----------
        context : OperationContext
            Operation scope and timeout.

        Returns
        -------
        ConnectionHealth
            Safe availability result.
        """
        raise NotImplementedError

    async def _events_until_deadline(
        self,
        iterator: AsyncIterator[dict[str, Any]],
        deadline: float,
        idle_timeout: float,
        usage: Usage | None,
        *,
        timeout_message: str = "Model request timed out.",
        idle_message: str = "Model request stopped making progress.",
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield provider chunks while enforcing idle and total deadlines.

        Parameters
        ----------
        iterator : AsyncIterator
            Provider event stream.
        deadline : float
            Absolute monotonic deadline.
        idle_timeout : float
            Maximum wait for one event.
        usage : Usage or None
            Usage known before this request.
        timeout_message, idle_message : str
            Display-safe total and inactivity timeout messages.

        Yields
        ------
        dict
            Raw decoded provider events.

        Raises
        ------
        ContractError
            If the total or idle timeout expires.
        """
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ContractError(
                    ErrorCode.TIMEOUT,
                    timeout_message,
                    transient=True,
                    usage=usage,
                )
            try:
                yield await asyncio.wait_for(
                    iterator.__anext__(), timeout=min(remaining, idle_timeout)
                )
            except StopAsyncIteration:
                return
            except TimeoutError:
                raise ContractError(
                    ErrorCode.TIMEOUT,
                    idle_message,
                    transient=True,
                    usage=usage,
                ) from None

    def _tool_declarations(self, request: ModelRequest) -> list[dict[str, Any]]:
        """Translate neutral tool definitions into provider function declarations.

        Parameters
        ----------
        request : ModelRequest
            Request with authorized, enabled tool schemas.

        Returns
        -------
        list of dict
            Common function name, description, and JSON parameter schema.
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in request.tools
        ]


def attach_usage(error: ContractError, usage: Usage | None) -> None:
    """Attach observed usage to a contract error when the error lacks it.

    Parameters
    ----------
    error : ContractError
        Provider error to update.
    usage : Usage or None
        Usage observed before the failure.

    Returns
    -------
    None
    """
    if error.usage is None and usage is not None:
        error.usage = usage
