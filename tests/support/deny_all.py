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
from amethyst.security.approval_store import ApprovalStore


class DenyAllApprovalService(ApprovalStore):
    def __init__(self) -> None:
        """Initialize deny all approval service state and dependencies.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__()

    async def request(self, proposal: ApprovalRequest) -> Approval:
        """Store an exact-action proposal for review.

        Parameters
        ----------
        proposal : ApprovalRequest
            Exact listed actions presented for user review.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
        if proposal.id in self._approvals:
            raise ContractError(ErrorCode.CONFLICT, "Approval ID already exists.")
        approval = Approval(proposal, ApprovalStatus.DENIED)
        self._approvals[proposal.id] = approval
        return approval

    async def decide(self, approval_id: str, *, granted: bool) -> Approval:
        """Record a trusted user decision on the selected proposal.

        Parameters
        ----------
        approval_id : str
            Identifier of the reviewed approval record.
        granted : bool
            Whether the user explicitly approved the listed actions.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
        approval = await self.inspect(approval_id)
        if granted:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Approval engine is disabled."
            )
        return approval

    async def revoke(self, approval_id: str) -> Approval:
        """Invalidate the selected permission or approval.

        Parameters
        ----------
        approval_id : str
            Identifier of the reviewed approval record.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
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
        """Provide the consume test fixture.

        Parameters
        ----------
        approval_id : str
            Identifier of the reviewed approval record.
        action_id : str
            Exact proposed action identifier.
        fingerprint : str
            Digest of the complete reviewed execution proposal.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        None
        """
        raise ContractError(
            ErrorCode.PERMISSION_DENIED, "Protected execution is disabled."
        )

    async def expire_task(self, task_id: str) -> None:
        """Expire authorizations associated with the selected task.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        None
        """
        for key, approval in self._approvals.items():
            if approval.request.task_id == task_id:
                self._approvals[key] = replace(approval, status=ApprovalStatus.EXPIRED)

    async def end_session(self, session_id: str) -> None:
        """Expire authorizations associated with the selected session.

        Parameters
        ----------
        session_id : str
            Identifier of the owning application/security session.

        Returns
        -------
        None
        """
        for key, approval in self._approvals.items():
            if approval.request.session_id == session_id:
                self._approvals[key] = replace(approval, status=ApprovalStatus.EXPIRED)
