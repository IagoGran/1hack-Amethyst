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
        """
        ...
