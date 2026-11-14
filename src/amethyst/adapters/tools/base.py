"""Base class for built-in tools; model generation uses a separate port."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

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


class Tool(ABC):
    """Define the stable role implemented by SQL, search, and retrieval tools.

    Notes
    -----
    Authorization and retries belong to the application. Adapters execute once.
    Structural implementations of the AgentTool port remain supported.
    """

    def _records_result(
        self,
        call_id: str,
        records: Sequence[object],
        sources: Sequence[Source],
        output_limit: int,
        *,
        truncated: bool = False,
    ) -> ToolResult:
        """Bound list-shaped results and retain only matching source metadata.

        Parameters
        ----------
        call_id : str
            Original tool invocation identifier.
        records : sequence of object
            Retrieved records, already subject to row/chunk policy.
        sources : sequence of Source
            One source per record in the same order.
        output_limit : int
            Maximum serialized UTF-8 content size.
        truncated : bool
            Whether earlier retrieval limits discarded data.

        Returns
        -------
        ToolResult
            Valid JSON records, aligned sources, and combined truncation state.
        """
        try:
            content, kept = bounded_json_records(records, max(0, output_limit))
        except ValueError:
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Tool result metadata exceeds the output limit.",
            ) from None
        return ToolResult(
            call_id, content, tuple(sources[:kept]), truncated or kept < len(records)
        )

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Describe the tool's name and accepted arguments.

        Parameters
        ----------
        None

        Returns
        -------
        ToolDefinition
            Model-visible schema.
        """
        raise NotImplementedError

    @abstractmethod
    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Execute a single invocation within the supplied operation limits.

        Parameters
        ----------
        call : ToolCall
            Validated invocation selected by the agent.
        context : OperationContext
            Task scope, timeout, and output limits.

        Returns
        -------
        ToolResult
            Result with source references and truncation metadata.
        """
        raise NotImplementedError
