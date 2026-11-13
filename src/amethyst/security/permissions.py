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


def fingerprint(payload: object) -> str:
    """SHA-256 of canonical JSON; callers include the entire execution proposal."""
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
        self.session_id = session_id
        self._grants: dict[str, ReadGrant] = {}
        self._closed = False

    def grant(
        self, tool_name: str, resource: str, *, recursive: bool = False
    ) -> ReadGrant:
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
        return tuple(self._grants.values())

    def revoke(self, grant_id: str) -> None:
        self._grants.pop(grant_id, None)

    def require(self, context: OperationContext, tool_name: str, resource: str) -> None:
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
        self._closed = True
        self._grants.clear()


class ApprovalEngine:
    """ApprovalService with task/session expiry and per-action consumption."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._tasks: set[str] = set()
        self._approvals: dict[str, Approval] = {}
        self._changed = asyncio.Condition()
        self._closed = False

    def open_task(self, task_id: str) -> None:
        if self._closed or task_id in self._tasks:
            raise ContractError(ErrorCode.CONFLICT, "Task cannot be registered.")
        self._tasks.add(task_id)

    async def _notify(self) -> None:
        async with self._changed:
            self._changed.notify_all()

    async def request(self, proposal: ApprovalRequest) -> Approval:
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

    async def inspect(self, approval_id: str) -> Approval:
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, "Approval not found.") from None

    async def decide(self, approval_id: str, *, granted: bool) -> Approval:
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
        approval = await self.inspect(approval_id)
        if approval.status not in {ApprovalStatus.CONSUMED, ApprovalStatus.EXPIRED}:
            approval = replace(approval, status=ApprovalStatus.REVOKED)
            self._approvals[approval_id] = approval
        await self._notify()
        return approval

    async def wait(self, approval_id: str) -> Approval:
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
        if session_id == self.session_id:
            self._closed = True
            for task_id in tuple(self._tasks):
                await self.expire_task(task_id)

    def inspect_all(self) -> tuple[Approval, ...]:
        return tuple(self._approvals.values())
