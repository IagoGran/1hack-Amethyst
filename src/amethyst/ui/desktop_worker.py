"""Keep the real application and all asyncio state on one persistent Qt thread."""

import asyncio
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal

from amethyst.application.runtime import DesktopRuntime
from amethyst.domain.contracts import ContractError, OperationContext, StartTask
from amethyst.ui.async_worker import AsyncThread


class DesktopWorker(AsyncThread):
    """Execute trusted UI commands while Qt remains responsive."""

    ready = Signal()
    result = Signal(str, object)
    failed = Signal(str, str)
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
            self.failed.emit("startup", "Unable to open the local application session.")
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
            self.failed.emit(action, self.runtime.redactor.redact(str(exc)))
        except Exception:
            self.failed.emit(
                action, "Operation failed. Check configuration and permissions."
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
            return agent.permissions.revoke(payload)
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
        if action == "send":
            return await self._send(payload)
        if action == "open":
            return await repos.conversations.load(payload)
        if self.busy:
            raise ValueError("Wait for the active task before changing configuration.")
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
            return runtime.set_workspace(Path(payload))
        if action == "grant_workspace" and agent.workspace:
            return agent.permissions.grant(
                "workspace.read", str(agent.workspace.root), recursive=True
            )
        if action in {"save_log", "delete_log"} and agent.diagnostics:
            operation = (
                agent.diagnostics.save_permanently
                if action == "save_log"
                else agent.diagnostics.delete
            )
            return operation(payload)
        raise ValueError("Unknown application command.")

    async def _send(self, request: StartTask) -> str:
        """Configure real adapters, follow task events, and retain its history.

        Parameters
        ----------
        request : StartTask
            User prompt and selected model/skills.

        Returns
        -------
        str
            Active conversation identifier.
        """
        if self.busy:
            raise ValueError("A task is already active.")
        assert self.runtime is not None
        self.busy = True
        try:
            await self.runtime.configure(request.model_connection_id)
            self.result.emit("warnings", tuple(self.runtime.warnings))
            task = await self.runtime.agent.start_task(request)
            self.task_id = task.id
            async for event in self.runtime.agent.events(task.id):
                self.event_received.emit(event)
            return request.conversation_id
        finally:
            self.task_id = None
            self.busy = False
