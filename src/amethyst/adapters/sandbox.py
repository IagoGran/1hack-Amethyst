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
        raise ContractError(
            ErrorCode.UNAVAILABLE, "Container execution is not configured."
        )
