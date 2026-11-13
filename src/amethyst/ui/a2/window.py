"""Desktop shell that connects A2 chat controls to the S0 application port."""

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
from amethyst.ui.a2.chat_page import A2ChatPage
from amethyst.ui.a2.task_worker import A2TaskWorker
from amethyst.ui.placeholder_page import PlaceholderPage
from amethyst.ui.sidebar import NavigationSidebar
from amethyst.ui.theme import APP_STYLE

PLACEHOLDERS = {
    "Conversations": "Conversation history requires a persistence service.",
    "Skills": "Skill management will use the skill repository port.",
    "Connections": "Model connections are not part of this fake preview.",
    "Permissions": "S0 denies protected actions by default.",
    "Task details": "Task state and ordered events come from the application port.",
}


class A2DesktopWindow(QMainWindow):
    """Coordinate A2 chat, navigation, and the asynchronous service bridge."""

    def __init__(self, service: ApplicationService) -> None:
        """Build the desktop shell around the supplied application service."""
        super().__init__()
        self._service = service
        self._conversation_id = str(uuid4())
        self._worker: A2TaskWorker | None = None
        self._last_sequence = 0
        self.setWindowTitle("Amethyst | A2 interaction preview")
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self._build_shell()
        self.setStyleSheet(APP_STYLE)

    def _build_shell(self) -> None:
        """Compose the shared navigation with the A2 chat and placeholders."""
        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._sidebar = NavigationSidebar()
        self._pages = QStackedWidget()
        self._chat = A2ChatPage()
        self._pages.addWidget(self._chat)
        self._indexes = {"Chat": 0}
        for title, description in PLACEHOLDERS.items():
            self._indexes[title] = self._pages.addWidget(
                PlaceholderPage(title, description)
            )
        layout.addWidget(self._sidebar)
        layout.addWidget(self._build_main_area(), 1)
        self.setCentralWidget(root)
        self._connect_controls()
        self._select_page("Chat")

    def _build_main_area(self) -> QWidget:
        """Add page heading and content stack beside the sidebar."""
        area = QWidget()
        area.setObjectName("mainArea")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(26, 18, 26, 18)
        layout.setSpacing(16)
        header = QHBoxLayout()
        self._page_title = QLabel("Chat")
        self._page_title.setObjectName("pageTitle")
        connected = QLabel("●  Local preview")
        connected.setObjectName("connectedPill")
        header.addWidget(self._page_title)
        header.addStretch(1)
        header.addWidget(connected)
        layout.addLayout(header)
        layout.addWidget(self._pages, 1)
        return area

    def _connect_controls(self) -> None:
        """Connect navigation, composer, cancellation, and budget actions."""
        self._sidebar.page_requested.connect(self._select_page)
        self._sidebar.new_conversation_requested.connect(self._new_conversation)
        self._chat.message_submitted.connect(self._start_task)
        self._chat.cancel_requested.connect(self._cancel_task)
        self._chat.budget_requested.connect(self._increase_budget)

    def _select_page(self, page: str) -> None:
        """Select a known page and update its title and sidebar state."""
        index = self._indexes.get(page, 0)
        self._pages.setCurrentIndex(index)
        self._page_title.setText(page)
        self._sidebar.set_active_page(page)

    def _new_conversation(self) -> None:
        """Start a fresh local conversation when no task is active."""
        if self._worker is not None and self._worker.isRunning():
            return
        self._conversation_id = str(uuid4())
        self._last_sequence = 0
        self._chat = A2ChatPage()
        self._pages.removeWidget(self._pages.widget(0))
        self._pages.insertWidget(0, self._chat)
        self._connect_chat_controls()
        self._select_page("Chat")

    def _connect_chat_controls(self) -> None:
        """Reconnect controls after replacing the transient chat page."""
        self._chat.message_submitted.connect(self._start_task)
        self._chat.cancel_requested.connect(self._cancel_task)
        self._chat.budget_requested.connect(self._increase_budget)

    def _start_task(self, prompt: str, scenario: str) -> None:
        """Start an application task and follow its ordered event stream."""
        if self._worker is not None and self._worker.isRunning():
            return
        self._last_sequence = 0
        self._chat.begin_task(prompt)
        request = StartTask(self._conversation_id, prompt, scenario)
        self._worker = A2TaskWorker(self._service, request, self)
        self._worker.event_received.connect(self._handle_event)
        self._worker.failed.connect(self._handle_failure)
        self._worker.control_acknowledged.connect(
            self._chat.show_control_acknowledgement
        )
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _handle_event(self, event: TaskEvent) -> None:
        """Deduplicate sequenced events before rendering them in the chat."""
        if event.sequence <= self._last_sequence:
            return
        self._last_sequence = event.sequence
        self._chat.render_event(event)

    def _cancel_task(self) -> None:
        """Request cancellation and show pending feedback until acknowledged."""
        if self._worker is not None:
            self._chat.set_cancelling()
            self._worker.cancel()

    def _increase_budget(self, tokens: int) -> None:
        """Forward the user's explicit token increase to the service."""
        if self._worker is not None:
            self._worker.increase_budget(tokens)

    def _handle_failure(self, message: str) -> None:
        """Display a safe service error and restore task controls."""
        self._chat.show_error(message)

    def _worker_finished(self) -> None:
        """Release the completed worker after its stream closes."""
        self._worker = None
