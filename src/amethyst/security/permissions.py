"""Session-scoped permissions and exact-action approvals.

All mutations run on one asyncio event loop; consuming an action has no await
between validation and consumption. No caller-supplied task ID grants access.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from amethyst.domain.contracts import (
    Approval,
    ApprovalRequest,
    ApprovalStatus,
    ContractError,
    ErrorCode,
    OperationContext,
)
from amethyst.security.approval_store import ApprovalStore


def fingerprint(payload: object) -> str:
    """SHA-256 of canonical JSON; callers include the entire execution proposal.

    Parameters
    ----------
    payload : object
        Operation-specific data; never log it wholesale.

    Returns
    -------
    str
        Text produced by the operation.
    """
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ReadGrant:
    id: str
    session_id: str
    tool_name: str
    resource: str
    recursive: bool = False


class PermissionService:
    """Only trusted user controls call grant/revoke; never expose these as tools."""

    def __init__(self, session_id: str) -> None:
        """Create the read-grant store for one application session.

        Parameters
        ----------
        session_id : str
            Identifier of the owning application/security session.

        Returns
        -------
        None
        """
        self.session_id = session_id
        self._grants: dict[str, ReadGrant] = {}
        self._closed = False

    def grant(
        self, tool_name: str, resource: str, *, recursive: bool = False
    ) -> ReadGrant:
        """Create an exact or recursive read grant from a trusted user control.

        Parameters
        ----------
        tool_name : str
            Registered tool name covered by the operation.
        resource : str
            Exact resource scope attached to this operation.
        recursive : bool
            Whether the grant covers descendants of its resource directory.

        Returns
        -------
        ReadGrant
            Session-scoped read grant.
        """
        if self._closed or not tool_name or not resource:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                "Permission session is closed or scope is invalid.",
            )
        if recursive:
            resource = str(Path(resource).resolve(strict=True))
        grant = ReadGrant(uuid4().hex, self.session_id, tool_name, resource, recursive)
        self._grants[grant.id] = grant
        return grant

    def inspect(self) -> tuple[ReadGrant, ...]:
        """Return current read grants without exposing mutable store state.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[ReadGrant, ...]
            Value produced by the operation.
        """
        return tuple(self._grants.values())

    def revoke(self, grant_id: str) -> None:
        """Remove the selected read grant idempotently.

        Parameters
        ----------
        grant_id : str
            Identifier of the read grant to revoke.

        Returns
        -------
        None
        """
        self._grants.pop(grant_id, None)

    def require(self, context: OperationContext, tool_name: str, resource: str) -> None:
        """Reject access outside the active session and granted resource scope.

        Parameters
        ----------
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.
        tool_name : str
            Registered tool name covered by the operation.
        resource : str
            Exact resource scope attached to this operation.

        Returns
        -------
        None
        """
        if not self._closed and context.session_id == self.session_id:
            for grant in self._grants.values():
                if grant.tool_name != tool_name:
                    continue
                if grant.resource == resource:
                    return
                if grant.recursive and Path(resource).is_absolute():
                    if Path(resource).resolve().is_relative_to(grant.resource):
                        return
        raise ContractError(
            ErrorCode.PERMISSION_DENIED, "Read permission is missing or revoked."
        )

    def close(self) -> None:
        """Invalidate the session and discard all read grants.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._closed = True
        self._grants.clear()


class ApprovalEngine(ApprovalStore):
    """ApprovalService with task/session expiry and per-action consumption."""

    def __init__(self, session_id: str) -> None:
        """Create session-local approval records and their change notification.

        Parameters
        ----------
        session_id : str
            Identifier of the owning application/security session.

        Returns
        -------
        None
        """
        self.session_id = session_id
        self._tasks: set[str] = set()
        super().__init__()
        self._changed = asyncio.Condition()
        self._closed = False

    def open_task(self, task_id: str) -> None:
        """Register a task before accepting its protected-action proposals.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        None
        """
        if self._closed or task_id in self._tasks:
            raise ContractError(ErrorCode.CONFLICT, "Task cannot be registered.")
        self._tasks.add(task_id)

    async def _notify(self) -> None:
        """Wake approval waiters after a trusted state change.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        async with self._changed:
            self._changed.notify_all()

    async def request(self, proposal: ApprovalRequest) -> Approval:
        """Store a proposal only for an active task in this security session.

        Parameters
        ----------
        proposal : ApprovalRequest
            Exact listed actions presented for user review.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
        if (
            self._closed
            or proposal.session_id != self.session_id
            or proposal.task_id not in self._tasks
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Approval task or session is inactive."
            )
        if proposal.id in self._approvals:
            raise ContractError(ErrorCode.CONFLICT, "Approval ID already exists.")
        if any(not a.fingerprint or not a.resource_scope for a in proposal.actions):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Approval requires a bound resource scope."
            )
        value = Approval(proposal)
        self._approvals[proposal.id] = value
        await self._notify()
        return value

    async def decide(self, approval_id: str, *, granted: bool) -> Approval:
        """Record the user decision for a pending proposal.

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
        if approval.status != ApprovalStatus.PENDING:
            raise ContractError(
                ErrorCode.CONFLICT, "Only a pending proposal may be decided."
            )
        value = replace(
            approval,
            status=ApprovalStatus.GRANTED if granted else ApprovalStatus.DENIED,
        )
        self._approvals[approval_id] = value
        await self._notify()
        return value

    async def revoke(self, approval_id: str) -> Approval:
        """Revoke an approval that has not been consumed or expired.

        Parameters
        ----------
        approval_id : str
            Identifier of the reviewed approval record.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
        approval = await self.inspect(approval_id)
        if approval.status not in {ApprovalStatus.CONSUMED, ApprovalStatus.EXPIRED}:
            approval = replace(approval, status=ApprovalStatus.REVOKED)
            self._approvals[approval_id] = approval
        await self._notify()
        return approval

    async def wait(self, approval_id: str) -> Approval:
        """Await a decision or invalidation of the pending approval.

        Parameters
        ----------
        approval_id : str
            Identifier of the reviewed approval record.

        Returns
        -------
        Approval
            Current approval state and its exact proposal.
        """
        async with self._changed:
            await self._changed.wait_for(
                lambda: self._approvals[approval_id].status != ApprovalStatus.PENDING
            )
        return await self.inspect(approval_id)

    async def consume(
        self,
        approval_id: str,
        action_id: str,
        fingerprint: str,
        context: OperationContext,
    ) -> None:
        # Do not await between lookup and consumption; revocation shares this loop.
        """Validate scope and consume the reviewed action without yielding.

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
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ContractError(ErrorCode.PERMISSION_DENIED, "Approval is missing.")
        request = approval.request
        action = next((a for a in request.actions if a.id == action_id), None)
        if (
            self._closed
            or approval.status != ApprovalStatus.GRANTED
            or context.session_id != self.session_id
            or request.session_id != context.session_id
            or request.task_id != context.task_id
            or request.task_id not in self._tasks
            or action is None
            or action.fingerprint != fingerprint
            or action_id in approval.consumed_action_ids
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                "Approval is invalid, changed, expired, or revoked.",
            )
        consumed = (*approval.consumed_action_ids, action_id)
        status = (
            ApprovalStatus.CONSUMED
            if len(consumed) == len(request.actions)
            else ApprovalStatus.GRANTED
        )
        self._approvals[approval_id] = replace(
            approval,
            status=status,
            consumed_action_ids=consumed,
        )

    async def expire_task(self, task_id: str) -> None:
        """Expire task approvals and discard their raw reviewed file content.

        Parameters
        ----------
        task_id : str
            Identifier of the task being inspected or controlled.

        Returns
        -------
        None
        """
        self._tasks.discard(task_id)
        for key, approval in self._approvals.items():
            if approval.request.task_id == task_id:
                # Discard raw reviewed workspace content after task completion.
                request = replace(
                    approval.request,
                    actions=tuple(
                        replace(
                            action,
                            summary="Expired action",
                            changes=(),
                            resource_scope=(),
                            fingerprint="",
                        )
                        for action in approval.request.actions
                    ),
                )
                self._approvals[key] = replace(
                    approval,
                    request=request,
                    status=ApprovalStatus.EXPIRED,
                )
        await self._notify()

    async def end_session(self, session_id: str) -> None:
        """Close the matching session and expire all registered tasks.

        Parameters
        ----------
        session_id : str
            Identifier of the owning application/security session.

        Returns
        -------
        None
        """
        if session_id == self.session_id:
            self._closed = True
            for task_id in tuple(self._tasks):
                await self.expire_task(task_id)

    def inspect_all(self) -> tuple[Approval, ...]:
        """Return approval snapshots for trusted inspection controls.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[Approval, ...]
            Value produced by the operation.
        """
        return tuple(self._approvals.values())
