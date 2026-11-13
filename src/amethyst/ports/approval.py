"""Atomic authorization boundary implemented by workstream B."""

from typing import Protocol

from amethyst.domain.contracts import Approval, ApprovalRequest, OperationContext


class ApprovalService(Protocol):
    async def request(self, proposal: ApprovalRequest) -> Approval: ...

    async def decide(self, approval_id: str, *, granted: bool) -> Approval: ...

    async def inspect(self, approval_id: str) -> Approval: ...

    async def revoke(self, approval_id: str) -> Approval: ...

    async def consume(
        self,
        approval_id: str,
        action_id: str,
        fingerprint: str,
        context: OperationContext,
    ) -> None:
        """Check scope, state, session, task and fingerprint; consume atomically.

        The trusted executor recomputes the fingerprint and file state. Changed,
        denied, revoked, expired, and consumed actions raise PERMISSION_DENIED.
        """
        ...

    async def expire_task(self, task_id: str) -> None: ...

    async def end_session(self, session_id: str) -> None: ...
