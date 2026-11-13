"""Thread bridge for asynchronous application-service calls."""

import asyncio

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from amethyst.domain.contracts import ContractError, StartTask
from amethyst.ports.application import ApplicationService


class TaskStreamWorker(QThread):
    """Consume an S0 task event stream away from the Qt event thread."""

    event_received = Signal(object)
    failed = Signal(str)

    def __init__(
        self, service: ApplicationService, request: StartTask, parent: QWidget
    ) -> None:
        """Store the service request and use the window as worker owner."""
        super().__init__(parent)
        self._service = service
        self._request = request

    def run(self) -> None:
        """Create a worker-local asyncio loop and forward its safe failures."""
        try:
            # The Qt event loop owns widgets; this loop keeps async port calls off it.
            asyncio.run(self._start_and_follow())
        except ContractError as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("The preview service failed unexpectedly.")

    async def _start_and_follow(self) -> None:
        """Start one task and forward its sequenced events to Qt."""
        task = await self._service.start_task(self._request)
        async for event in self._service.events(task.id):
            self.event_received.emit(event)
