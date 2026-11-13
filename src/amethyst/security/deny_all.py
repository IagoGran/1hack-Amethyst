"""Fail-closed placeholder, not an implementation of the approval policy."""

from dataclasses import replace

from amethyst.domain.contracts import (
    Approval,
    ApprovalRequest,
    ApprovalStatus,
    ContractError,
    ErrorCode,
    OperationContext,
)


class DenyAllApprovalService:
    def __init__(self) -> None:
        self._approvals: dict[str, Approval] = {}

    async def request(self, proposal: ApprovalRequest) -> Approval:
        if proposal.id in self._approvals:
            raise ContractError(ErrorCode.CONFLICT, "Approval ID already exists.")
        approval = Approval(proposal, ApprovalStatus.DENIED)
        self._approvals[proposal.id] = approval
        return approval

    async def inspect(self, approval_id: str) -> Approval:
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, "Approval not found.") from None

    async def decide(self, approval_id: str, *, granted: bool) -> Approval:
        approval = await self.inspect(approval_id)
        if granted:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Approval engine is disabled."
            )
        return approval

    async def revoke(self, approval_id: str) -> Approval:
        approval = replace(
            await self.inspect(approval_id), status=ApprovalStatus.REVOKED
        )
        self._approvals[approval_id] = approval
        return approval

    async def consume(
        self,
        approval_id: str,
        action_id: str,
        fingerprint: str,
        context: OperationContext,
    ) -> None:
        raise ContractError(
            ErrorCode.PERMISSION_DENIED, "Protected execution is disabled."
        )

    async def expire_task(self, task_id: str) -> None:
        for key, approval in self._approvals.items():
            if approval.request.task_id == task_id:
                self._approvals[key] = replace(approval, status=ApprovalStatus.EXPIRED)

    async def end_session(self, session_id: str) -> None:
        for key, approval in self._approvals.items():
            if approval.request.session_id == session_id:
                self._approvals[key] = replace(approval, status=ApprovalStatus.EXPIRED)
