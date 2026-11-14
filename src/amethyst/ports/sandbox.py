"""Container invocation boundary. There is no host execution mode."""

from typing import Protocol

from amethyst.domain.contracts import OperationContext, SandboxRequest, SandboxResult


class Sandbox(Protocol):
    async def run(
        self, request: SandboxRequest, context: OperationContext
    ) -> SandboxResult:
        """Enforce authorization, workspace and network scope, limits and cancellation.

        Cancellation must stop the container before acknowledgement. An uncertain
        outcome must be reported explicitly and must never be retried automatically.

        Parameters
        ----------
        request : SandboxRequest
            Typed request describing the operation and its scope.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        SandboxResult
            Value produced by the operation.
        """
        ...
