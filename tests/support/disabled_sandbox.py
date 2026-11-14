"""Fail-closed placeholder until a validated container runtime is selected."""

from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    OperationContext,
    SandboxRequest,
    SandboxResult,
)


class DisabledSandbox:
    async def run(
        self, request: SandboxRequest, context: OperationContext
    ) -> SandboxResult:
        """Provide the run test fixture.

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
        raise ContractError(
            ErrorCode.UNAVAILABLE, "Container execution is not configured."
        )
