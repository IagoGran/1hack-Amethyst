"""Keep the real application and all asyncio state on one persistent Qt thread."""

import asyncio
import traceback
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal

from amethyst.application.runtime import DesktopRuntime
from amethyst.domain.contracts import (
    ActionRecord,
    ApprovalRequest,
    ApprovalStatus,
    ContractError,
    Conversation,
    ErrorCode,
    OperationContext,
    StartTask,
)
from amethyst.ui.async_worker import AsyncThread


class DesktopWorker(AsyncThread):
    """Execute trusted UI commands while Qt remains responsive."""

    ready = Signal()
    result = Signal(str, object)
    failed = Signal(str, str, object)
    event_received = Signal(object)

    def __init__(self, database: Path | None = None, **options) -> None:
        """Remember bootstrap options without opening services on Qt's thread.

        Parameters
        ----------
        database : Path, optional
            Application database override.
        **options : dict
            Workspace and sandbox options.

        Returns
        -------
        None
        """
        super().__init__()
        self.database = database
        self.options = options
        self.loop: asyncio.AbstractEventLoop | None = None
        self.runtime: DesktopRuntime | None = None
        self.task_id: str | None = None
        self.active_conversation_id: str | None = None
        self.busy = False

    def run(self) -> None:
        """Own a single event loop until asynchronous session shutdown finishes.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._open_loop()
        assert self.loop is not None
        try:
            self.runtime = self.loop.run_until_complete(
                DesktopRuntime.open(self.database, **self.options)
            )
            self.ready.emit()
            self.loop.run_forever()
        except Exception:
            self.failed.emit(
                "startup", "Unable to open the local application session.", ()
            )
        finally:
            if self.runtime is not None:
                self.loop.run_until_complete(self.runtime.close())
            self._close_loop()

    def submit(self, action: str, payload: object = None) -> None:
        """Schedule a UI command without sharing application state across threads.

        Parameters
        ----------
        action : str
            Trusted command name.
        payload : object
            Command-specific input.

        Returns
        -------
        None
        """
        if self.loop is not None and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._execute(action, payload), self.loop)

    async def _execute(self, action: str, payload) -> None:
        """Dispatch commands and emit only filtered failures to Qt.

        Parameters
        ----------
        action : str
            Trusted command name.
        payload : object
            Command-specific input.

        Returns
        -------
        None
        """
        assert self.runtime is not None
        try:
            value = await self._dispatch(action, payload)
            self.result.emit(action, value)
        except ContractError as exc:
            self.failed.emit(
                action,
                self.runtime.redactor.redact(str(exc)),
                _safe_stacktrace(exc),
            )
        except Exception as error:
            self.failed.emit(
                action,
                "Operation failed. Check configuration and permissions.",
                _safe_stacktrace(error),
            )

    async def _dispatch(self, action: str, payload):
        """Route application and repository operations on their owning loop.

        Parameters
        ----------
        action : str
            Trusted command name.
        payload : object
            Command-specific input.

        Returns
        -------
        object
            Detached operation result.
        """
        assert self.runtime is not None
        runtime = self.runtime
        agent = runtime.agent
        repos = runtime.repositories
        if action == "close":
            await runtime.close()
            assert self.loop is not None
            self.loop.call_soon(self.loop.stop)
            return None
        if action == "cancel" and self.task_id:
            return await agent.cancel_task(self.task_id)
        if action == "budget" and self.task_id:
            return await agent.increase_budget(self.task_id, payload)
        if action == "decide":
            return await agent.approvals.decide(payload[0], granted=payload[1])
        if action == "revoke_approval":
            return await agent.approvals.revoke(payload)
        if action == "revoke_grant":
            workspace_grant_ids = {
                grant.id
                for grant in agent.permissions.inspect()
                if grant.tool_name == "workspace.read"
            }
            if payload in workspace_grant_ids and self.active_conversation_id:
                agent.revoke_conversation_workspace(self.active_conversation_id)
            agent.permissions.revoke(payload)
            if payload in workspace_grant_ids and self.active_conversation_id:
                conversation = await repos.conversations.load(
                    self.active_conversation_id
                )
                if conversation.workspace_read_granted:
                    await repos.conversations.save(
                        replace(conversation, workspace_read_granted=False)
                    )
            return None
        if action == "snapshot":
            return {
                "conversations": await repos.conversations.list(),
                "connections": await repos.connections.list(),
                "skills": await repos.skills.list(),
                "grants": agent.permissions.inspect(),
                "approvals": agent.approvals.inspect_all(),
                "memory_only": runtime.credentials.memory_only,
                "limits": agent.limits,
                "workspace": str(agent.workspace.root) if agent.workspace else None,
                "sandbox_enabled": bool(agent.sandbox and agent.sandbox.enabled),
                "logs": agent.diagnostics.list() if agent.diagnostics else (),
            }
        if action == "resources":
            return await runtime.sample_resources()
        if action == "send":
            return await self._send(payload)
        if action == "open":
            conversation = await repos.conversations.load(payload)
            await self._activate_conversation(conversation)
            return conversation
        if action == "activate_conversation":
            conversation = (
                await self._conversation(payload) if payload else None
            )
            await self._activate_conversation(conversation)
            return None
        if self.busy:
            raise ValueError("Wait for the active task before changing configuration.")
        return await self._dispatch_idle(action, payload)

    async def _dispatch_idle(self, action: str, payload):
        """Dispatch non-task settings, workspace, and model-management actions.

        Parameters
        ----------
        action : str
            Trusted command name.
        payload : object
            Command-specific input.

        Returns
        -------
        object
            Detached operation result.
        """
        assert self.runtime is not None
        runtime = self.runtime
        agent = runtime.agent
        repos = runtime.repositories
        if action == "ollama_list":
            return await runtime.list_local_ollama_models()
        if action == "ollama_pull":
            await runtime.pull_local_ollama_model(
                str(payload),
                lambda status: self.event_received.emit(("ollama_progress", status)),
            )
            return await runtime.list_local_ollama_models()
        if action == "undo_last":
            return await self._undo_last(str(payload))
        if action == "git_branches":
            return runtime.git_branches()
        if action == "delete_conversation":
            return await repos.conversations.delete(payload)
        if action == "save_connection":
            return await runtime.save_connection(*payload)
        if action == "delete_connection":
            return await runtime.connections.delete(payload)
        if action == "test_connection":
            async with asyncio.timeout(agent.limits.tool_seconds):
                return await runtime.connections.test(
                    payload, OperationContext(uuid4().hex, agent.session_id)
                )
        if action == "save_skill":
            return await repos.skills.save(payload)
        if action == "save_limits":
            return runtime.set_limits(payload)
        if action == "delete_skill":
            return await repos.skills.delete(payload)
        if action == "workspace":
            conversation_id, path = payload
            conversation = await self._conversation(conversation_id)
            root = Path(path).resolve(strict=True)
            if conversation.workspace_root == str(root):
                await self._activate_conversation(conversation)
                return conversation
            runtime.set_workspace(root)
            updated = replace(
                conversation,
                workspace_root=str(runtime.agent.workspace.root),
                workspace_read_granted=False,
                undo_records=(),
            )
            await repos.conversations.save(updated)
            self.active_conversation_id = conversation_id
            return updated
        if action == "workspace_access":
            conversation_id, granted = payload
            conversation = await self._conversation(conversation_id)
            if not conversation.workspace_root:
                raise ValueError("Choose a workspace for this chat first.")
            if granted:
                runtime.set_workspace(Path(conversation.workspace_root))
                agent.permissions.grant(
                    "workspace.read", str(agent.workspace.root), recursive=True
                )
            else:
                runtime.clear_workspace()
            updated = replace(conversation, workspace_read_granted=bool(granted))
            await repos.conversations.save(updated)
            self.active_conversation_id = conversation_id
            return updated
        if action in {"save_log", "delete_log"} and agent.diagnostics:
            operation = (
                agent.diagnostics.save_permanently
                if action == "save_log"
                else agent.diagnostics.delete
            )
            return operation(payload)
        raise ValueError("Unknown application command.")

    async def _send(self, request: StartTask) -> Conversation:
        """Configure real adapters, follow task events, and retain its history.

        Parameters
        ----------
        request : StartTask
            User prompt and selected model/skills.

        Returns
        -------
        Conversation
            Persisted conversation after task finalization.
        """
        if self.busy:
            raise ValueError("A task is already active.")
        assert self.runtime is not None
        self.busy = True
        try:
            await self.runtime.configure(request.model_connection_id)
            conversation = await self._conversation(request.conversation_id)
            actions = conversation.action_history
            if (
                conversation.model_connection_id
                and conversation.model_connection_id != request.model_connection_id
            ):
                change = ActionRecord(
                    "model.selection",
                    "changed",
                    f"Switched model to {request.model_connection_id}",
                )
                actions = (*actions, change)
                self.event_received.emit(change)
            await self.runtime.repositories.conversations.save(
                replace(
                    conversation,
                    model_connection_id=request.model_connection_id,
                    action_history=actions,
                )
            )
            self.result.emit("warnings", tuple(self.runtime.warnings))
            task = await self.runtime.agent.start_task(request)
            self.task_id = task.id
            async for event in self.runtime.agent.events(task.id):
                self.event_received.emit(event)
            return await self.runtime.repositories.conversations.load(
                request.conversation_id
            )
        finally:
            self.task_id = None
            self.busy = False

    async def _conversation(self, identifier: str) -> Conversation:
        """Load an existing conversation or prepare its first saved turn.

        Parameters
        ----------
        identifier : str
            Conversation identifier supplied by the trusted desktop.

        Returns
        -------
        Conversation
            Existing or new conversation record.
        """
        assert self.runtime is not None
        try:
            return await self.runtime.repositories.conversations.load(identifier)
        except ContractError as error:
            if error.code != ErrorCode.NOT_FOUND:
                raise
        return Conversation(identifier, "New conversation")

    async def _activate_conversation(
        self, conversation: Conversation | None
    ) -> None:
        """Restore one chat's workspace and its persisted, revocable read grant.

        Parameters
        ----------
        conversation : Conversation or None
            Conversation to activate, or None for a fresh chat.

        Returns
        -------
        None
        """
        assert self.runtime is not None
        self.runtime.clear_workspace()
        self.active_conversation_id = conversation.id if conversation else None
        if not conversation or not conversation.workspace_root:
            return
        try:
            self.runtime.set_workspace(Path(conversation.workspace_root))
        except (ContractError, OSError):
            self.runtime.clear_workspace()
            return
        if conversation.workspace_read_granted:
            self.runtime.agent.permissions.grant(
                "workspace.read",
                str(self.runtime.agent.workspace.root),
                recursive=True,
            )

    async def _undo_last(self, conversation_id: str) -> Conversation:
        """Propose and apply the latest inverse diff after explicit review.

        Parameters
        ----------
        conversation_id : str
            Conversation whose retained file snapshot is being restored.

        Returns
        -------
        Conversation
            Updated conversation with the consumed undo record removed.

        Raises
        ------
        ContractError
            If the workspace grant, snapshot, or reviewed approval is invalid.
        """
        assert self.runtime is not None
        conversation = await self.runtime.repositories.conversations.load(
            conversation_id
        )
        workspace = self.runtime.agent.workspace
        if (
            conversation_id != self.active_conversation_id
            or workspace is None
            or not conversation.workspace_read_granted
            or not conversation.undo_records
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                "Open the chat and grant its workspace before reverting a change.",
            )
        undo = conversation.undo_records[-1]
        task_id = uuid4().hex
        approval_id = uuid4().hex
        context = OperationContext(
            task_id,
            self.runtime.agent.session_id,
            self.runtime.agent.limits.tool_seconds,
        )
        edit = workspace.propose(undo.path, undo.previous_content, context)
        proposal = ApprovalRequest(
            approval_id,
            task_id,
            self.runtime.agent.session_id,
            (edit.action,),
        )
        approvals = self.runtime.agent.approvals
        approvals.register_task(task_id)
        try:
            await approvals.request(proposal)
            self.event_received.emit(proposal)
            decision = await approvals.wait(approval_id)
            if decision.status != ApprovalStatus.GRANTED:
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED, "Revert was denied or revoked."
                )
            await workspace.apply(edit, approval_id, context)
        finally:
            await approvals.expire_task(task_id)
        updated = replace(
            conversation,
            undo_records=conversation.undo_records[:-1],
            action_history=(
                *conversation.action_history,
                ActionRecord(
                    "workspace.undo",
                    "completed",
                    f"Restored {undo.path}",
                    (undo.path,),
                ),
            ),
        )
        await self.runtime.repositories.conversations.save(updated)
        return updated


def _safe_stacktrace(error: Exception) -> tuple[str, ...]:
    """Return bounded frame names without source lines or exception arguments.

    Parameters
    ----------
    error : Exception
        Failure with a Python traceback.

    Returns
    -------
    tuple of str
        Safe frame locations for expandable local diagnostics.
    """
    frames = traceback.extract_tb(error.__traceback__)[-12:]
    return tuple(
        f"{frame.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:"
        f"{frame.lineno} in {frame.name}"
        for frame in frames
    )
