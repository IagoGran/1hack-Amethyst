"""Atomic authorization boundary implemented by workstream B."""

from typing import Protocol

from amethyst.domain.contracts import Approval, ApprovalRequest, OperationContext


class ApprovalService(Protocol):
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
        ...

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
        ...

    async def inspect(self, approval_id: str) -> Approval:
        """Return the selected record without changing its authorization state.

        Parameters
        ----------
        approval_id : str
            Identifier of the reviewed approval record.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
        ...

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
        ...

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
        ...

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
        ...

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
        ...
