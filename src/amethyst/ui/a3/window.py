"""A3 desktop preview with local conversation history and fake responses."""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from amethyst.adapters.fakes import FakeApplicationService
from amethyst.domain.contracts import Conversation
from amethyst.ports.persistence import ConversationRepository
from amethyst.ui.branding import APP_ICON_PATH
from amethyst.ui.a3.chat_page import A3ChatPage
from amethyst.ui.a3.conversation_worker import ConversationWorker
from amethyst.ui.a3.history_page import ConversationHistoryPage
from amethyst.ui.placeholder_page import PlaceholderPage
from amethyst.ui.sidebar import NavigationSidebar
from amethyst.ui.theme import APP_STYLE

PLACEHOLDER_PAGES = {
    "Skills": "Skill management will use the skill repository port.",
    "Connections": "Model connections are not part of this fake preview.",
    "Permissions": "S0 denies protected actions by default.",
    "Task details": "Task status is supplied by the application port.",
}


class A3DesktopWindow(QMainWindow):
    """Connect the history UI to a repository and a deterministic fake service."""

    def __init__(self, repository: ConversationRepository) -> None:
        """Build the A3 shell and schedule an initial history load."""
        super().__init__()
        self._repository = repository
        self._service = FakeApplicationService(
            chunks=(
                "This is a deterministic preview response. ",
                "The conversation is stored locally for later resumption.",
            )
        )
        self._conversation_id: str | None = None
        self._worker: ConversationWorker | None = None
        self._worker_action: str | None = None
        self.setWindowTitle("Amethyst | A3 conversation history preview")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self._build_shell()
        self.setStyleSheet(APP_STYLE)
        self._launch_worker("list")

    def _build_shell(self) -> None:
        """Compose navigation, chat, history, and placeholder pages."""
        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._sidebar = NavigationSidebar()
        self._pages = QStackedWidget()
        self._chat = A3ChatPage()
        self._history = ConversationHistoryPage()
        self._pages.addWidget(self._chat)
        self._pages.addWidget(self._history)
        self._indexes = {"Chat": 0, "Conversations": 1}
        for title, description in PLACEHOLDER_PAGES.items():
            self._indexes[title] = self._pages.addWidget(
                PlaceholderPage(title, description)
            )
        layout.addWidget(self._sidebar)
        layout.addWidget(self._build_main_area(), 1)
        self.setCentralWidget(root)
        self._connect_controls()
        self._select_page("Chat")

    def _build_main_area(self) -> QWidget:
        """Add a prominent page header and content stack beside navigation."""
        area = QWidget()
        area.setObjectName("mainArea")
        layout = QVBoxLayout(area)
        layout.setContentsMargins(24, 16, 26, 22)
        layout.setSpacing(18)
        header_frame = QWidget()
        header_frame.setObjectName("topHeader")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(14)
        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        eyebrow = QLabel("AMETHYST WORKSPACE")
        eyebrow.setObjectName("pageEyebrow")
        self._page_title = QLabel("Chat")
        self._page_title.setObjectName("pageTitle")
        subtitle = QLabel("Your local coding workspace")
        subtitle.setObjectName("pageSubtitle")
        title_column.addWidget(eyebrow)
        title_column.addWidget(self._page_title)
        title_column.addWidget(subtitle)
        header.addLayout(title_column)
        local = QLabel("●  Local preview")
        local.setObjectName("connectedPill")
        header.addStretch(1)
        header.addWidget(local)
        layout.addWidget(header_frame)
        layout.addWidget(self._pages, 1)
        return area

    def _connect_controls(self) -> None:
        """Connect navigation, history actions, and message submission."""
        self._sidebar.page_requested.connect(self._select_page)
        self._sidebar.new_conversation_requested.connect(self._new_conversation)
        self._sidebar.recent_conversation_requested.connect(self._open_conversation)
        self._chat.message_submitted.connect(self._send_message)
        self._history.open_requested.connect(self._open_conversation)
        self._history.delete_requested.connect(self._confirm_delete)

    def _select_page(self, page: str) -> None:
        """Select a page and update its title and active navigation item."""
        self._pages.setCurrentIndex(self._indexes.get(page, 0))
        self._page_title.setText(page)
        self._sidebar.set_active_page(page)

    def _new_conversation(self) -> None:
        """Reset the chat to a new conversation without deleting saved data."""
        if self._is_busy():
            return
        self._conversation_id = None
        self._chat.reset()
        self._select_page("Chat")

    def _send_message(self, prompt: str) -> None:
        """Persist a user turn and stream a fake reply into the chat page."""
        if self._is_busy():
            return
        self._chat.begin_turn(prompt)
        self._launch_worker(
            "send", prompt=prompt, conversation_id=self._conversation_id
        )

    def _open_conversation(self, conversation_id: str) -> None:
        """Load a selected conversation and prepare its prompt for resumption."""
        if not self._is_busy():
            self._launch_worker("open", conversation_id=conversation_id)

    def _confirm_delete(self, conversation_id: str) -> None:
        """Ask for confirmation before deleting the selected saved record."""
        title = "Delete conversation?"
        message = "This permanently deletes the selected local conversation."
        answer = QMessageBox.question(self, title, message)
        if answer == QMessageBox.StandardButton.Yes and not self._is_busy():
            if conversation_id == self._conversation_id:
                self._conversation_id = None
                self._chat.reset()
            self._launch_worker("delete", conversation_id=conversation_id)

    def _launch_worker(
        self,
        action: str,
        *,
        conversation_id: str | None = None,
        prompt: str | None = None,
    ) -> None:
        """Create one background repository or chat worker and connect signals."""
        if self._is_busy():
            return
        self._worker_action = action
        self._worker = ConversationWorker(
            self._repository,
            self._service,
            action,
            self,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        self._worker.conversations_loaded.connect(self._history.set_conversations)
        self._worker.conversations_loaded.connect(
            self._sidebar.set_recent_conversations
        )
        self._worker.conversation_loaded.connect(self._show_conversation)
        self._worker.conversation_ready.connect(self._set_conversation_id)
        self._worker.message_delta.connect(self._chat.append_delta)
        self._worker.task_finished.connect(self._finish_turn)
        self._worker.deleted.connect(self._history.show_deleted)
        self._worker.failed.connect(self._show_error)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def _show_conversation(self, conversation: Conversation) -> None:
        """Set the active ID and display persisted messages for resumption."""
        self._conversation_id = conversation.id
        self._chat.load_conversation(conversation)
        self._select_page("Chat")

    def _set_conversation_id(self, conversation_id: str) -> None:
        """Remember the conversation ID created or continued by the worker."""
        self._conversation_id = conversation_id

    def _show_error(self, message: str) -> None:
        """Display a safe failure in chat or history, based on the active page."""
        if self._pages.currentIndex() == self._indexes["Chat"]:
            self._chat.show_error(message)
        else:
            self._history.show_error(message)

    def _worker_finished(self) -> None:
        """Restore the chat composer after an operation and release the worker."""
        self._worker = None
        self._worker_action = None

    def _finish_turn(self, succeeded: bool) -> None:
        """Show whether the streamed turn was persisted successfully."""
        self._chat.finish_turn("Saved" if succeeded else "Failed")

    def _is_busy(self) -> bool:
        """Report whether a repository or generation operation is active."""
        return self._worker is not None and self._worker.isRunning()
