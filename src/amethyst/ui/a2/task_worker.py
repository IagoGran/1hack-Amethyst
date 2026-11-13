"""Qt thread bridge for A2 tasks and task controls."""

import asyncio
import concurrent.futures
from collections.abc import Coroutine
from typing import Any

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from amethyst.domain.contracts import ContractError, StartTask, TaskEvent
from amethyst.domain.tasks import Task
from amethyst.ports.application import ApplicationService


class A2TaskWorker(QThread):
    """Keep async service calls off the Qt event thread and emit safe results."""

    event_received = Signal(object)
    control_acknowledged = Signal(str)
    failed = Signal(str)

    def __init__(
        self, service: ApplicationService, request: StartTask, parent: QWidget
    ) -> None:
        """Store task inputs and initialize cross-thread loop handles."""
        super().__init__(parent)
        self._service = service
        self._request = request
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task_id: str | None = None

    def run(self) -> None:
        """Run task subscription in a dedicated asyncio loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            # The service and all its asyncio primitives stay on this loop's thread.
            self._loop.run_until_complete(self._start_and_follow())
        except ContractError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("The preview service failed unexpectedly.")
        finally:
            self._loop.close()

    def cancel(self) -> None:
        """Queue a cancellation request on the worker's own event loop."""
        self._submit_control(self._cancel_task())

    def increase_budget(self, tokens: int) -> None:
        """Queue a user-requested budget increase on the worker loop."""
        self._submit_control(self._increase_budget(tokens))

    async def _start_and_follow(self) -> None:
        """Start the task, publish its ID, and stream ordered events."""
        task = await self._service.start_task(self._request)
        self._task_id = task.id
        async for event in self._service.events(task.id):
            self.event_received.emit(event)

    def _submit_control(self, coroutine: Coroutine[Any, Any, Task]) -> None:
        """Schedule a control call without blocking the GUI thread."""
        if self._loop is None or self._task_id is None:
            return
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        future.add_done_callback(self._control_finished)

    async def _cancel_task(self) -> None:
        """Ask the application service to cancel and await its acknowledgement."""
        if self._task_id:
            task = await self._service.cancel_task(self._task_id)
            self.control_acknowledged.emit(task.status.value)

    async def _increase_budget(self, tokens: int) -> None:
        """Request an explicit budget increase and emit the accepted state."""
        if self._task_id:
            task = await self._service.increase_budget(self._task_id, tokens)
            self.control_acknowledged.emit(task.status.value)

    def _control_finished(self, future: concurrent.futures.Future[object]) -> None:
        """Forward safe service errors from a control request to the UI."""
        try:
            future.result()
        except ContractError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("The task control request failed.")
