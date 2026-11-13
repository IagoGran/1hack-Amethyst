"""Top-level desktop shell and application-service coordinator."""

from uuid import uuid4

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import StartTask, TaskEvent
from amethyst.ports.application import ApplicationService
from amethyst.ui.chat_page import ChatPage
from amethyst.ui.placeholder_page import PlaceholderPage
from amethyst.ui.sidebar import NavigationSidebar
from amethyst.ui.theme import APP_STYLE
from amethyst.ui.worker import TaskStreamWorker

PLACEHOLDER_DESCRIPTIONS = {
    "Conversations": (
        "Conversation list, resume, and delete actions will use the persistence port."
    ),
    "Skills": "Skill management will use the skill repository port.",
    "Connections": "Model and data-source settings will use configuration ports.",
    "Permissions": (
        "Approval controls use the approval port; S0 denies protected "
        "actions by default."
    ),
    "Task details": "Task status and ordered events come from the S0 application port.",
}


class DesktopWindow(QMainWindow):
    """Connect navigation and chat views to the S0 application-service port."""

    def __init__(self, service: ApplicationService) -> None:
        """Build the shell, pages, and event-loop bridge for the preview."""
        super().__init__()
        self._service = service
        self._conversation_id = str(uuid4())
        self._worker: TaskStreamWorker | None = None
        self._last_event_sequence = 0
        self.setWindowTitle("Amethyst | Desktop preview")
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self.setAccessibleName("Amethyst desktop preview")
        self._build_shell()
        self.setStyleSheet(APP_STYLE)

    def _build_shell(self) -> None:
        """Place the navigation sidebar and stacked screen area."""
        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._sidebar = NavigationSidebar()
        self._pages = QStackedWidget()
        self._chat_page = ChatPage()
        self._pages.addWidget(self._chat_page)
        self._page_indexes = {"Chat": 0}
        self._add_placeholder_pages()
        main_area = self._build_main_area()
        layout.addWidget(self._sidebar)
        layout.addWidget(main_area, 1)
        self.setCentralWidget(root)
        self._connect_controls()
        self._select_page("Chat")

    def _build_main_area(self) -> QWidget:
        """Place the page title, connection indicator, and screen stack."""
        main_area = QWidget()
        main_area.setObjectName("mainArea")
        layout = QVBoxLayout(main_area)
        layout.setContentsMargins(26, 18, 26, 18)
        layout.setSpacing(16)
        topbar = QHBoxLayout()
        self._page_title = QLabel("Chat")
        self._page_title.setObjectName("pageTitle")
        connected = QLabel("●  Workspace connected")
        connected.setObjectName("connectedPill")
        topbar.addWidget(self._page_title)
        topbar.addStretch(1)
        topbar.addWidget(connected)
        layout.addLayout(topbar)
        layout.addWidget(self._pages, 1)
        return main_area

    def _add_placeholder_pages(self) -> None:
        """Register each A1 destination not yet wired to a service."""
        for title, description in PLACEHOLDER_DESCRIPTIONS.items():
            page = PlaceholderPage(title, description)
            self._page_indexes[title] = self._pages.addWidget(page)

    def _connect_controls(self) -> None:
        """Connect sidebar and chat signals to shell actions."""
        self._sidebar.page_requested.connect(self._select_page)
        self._sidebar.new_conversation_requested.connect(self._new_conversation)
        self._chat_page.message_submitted.connect(self._start_task)

    def _select_page(self, page: str) -> None:
        """Change the visible screen and active navigation item."""
        self._pages.setCurrentIndex(self._page_indexes.get(page, 0))
        self._page_title.setText(page)
        self._sidebar.set_active_page(page)

    def _new_conversation(self) -> None:
        """Reset transient chat state and create a new conversation ID."""
        if self._worker is not None and self._worker.isRunning():
            return
        self._conversation_id = str(uuid4())
        self._last_event_sequence = 0
        self._chat_page.reset()
        self._select_page("Chat")

    def _start_task(self, message: str) -> None:
        """Submit a chat request and follow its ordered event stream."""
        if self._worker is not None and self._worker.isRunning():
            return
        self._last_event_sequence = 0
        self._chat_page.prepare_task(message)
        request = StartTask(
            conversation_id=self._conversation_id,
            request=message,
            model_connection_id="development-fake",
        )
        self._worker = TaskStreamWorker(self._service, request, self)
        self._worker.event_received.connect(self._handle_event)
        self._worker.failed.connect(self._handle_failure)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _handle_event(self, event: TaskEvent) -> None:
        """Ignore duplicate sequence numbers before forwarding typed events."""
        if event.sequence <= self._last_event_sequence:
            return
        self._last_event_sequence = event.sequence
        self._chat_page.render_event(event)

    def _handle_failure(self, message: str) -> None:
        """Show a safe service error and restore the composer controls."""
        self._chat_page.set_status("Failed")
        self._chat_page.set_busy(False)
        self._chat_page.render_error(message)

    def _worker_finished(self) -> None:
        """Release the finished worker and return focus to the composer."""
        self._chat_page.set_busy(False)
        self._chat_page.focus_prompt()
        self._worker = None
