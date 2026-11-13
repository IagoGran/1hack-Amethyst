"""Conversation list and actions for the A3 history workflow."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Conversation
from amethyst.ui.base_page import BasePage


class ConversationHistoryPage(BasePage):
    """List saved conversations and request open or delete actions."""

    open_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build an accessible list with explicit open and delete buttons."""
        super().__init__("Conversations", parent)
        self._build_content()

    def _build_content(self) -> None:
        """Arrange history explanation, list, and action feedback."""
        intro = QLabel("Saved conversations stay on this device until you delete them.")
        intro.setObjectName("muted")
        self.content_layout.addWidget(intro)
        self._list = QListWidget()
        self._list.setObjectName("conversationList")
        self._list.setAccessibleName("Saved conversations")
        self._list.setSpacing(6)
        self._list.currentItemChanged.connect(self._update_actions)
        self._list.itemDoubleClicked.connect(self._open_selected)
        self.content_layout.addWidget(self._list, 1)
        actions = QHBoxLayout()
        self._feedback = QLabel("Loading conversations…")
        self._feedback.setObjectName("muted")
        actions.addWidget(self._feedback, 1)
        self._open = QPushButton("Open / resume")
        self._open.setObjectName("secondaryAction")
        self._open.setEnabled(False)
        self._open.setAccessibleName("Open or resume selected conversation")
        self._open.clicked.connect(self._open_selected)
        actions.addWidget(self._open)
        self._delete = QPushButton("Delete")
        self._delete.setObjectName("dangerAction")
        self._delete.setEnabled(False)
        self._delete.setAccessibleName("Delete selected conversation")
        self._delete.clicked.connect(self._delete_selected)
        actions.addWidget(self._delete)
        self.content_layout.addLayout(actions)

    def set_conversations(self, values: tuple[Conversation, ...]) -> None:
        """Replace list contents with repository snapshots and message counts."""
        selected_id = self._selected_id()
        self._list.clear()
        for conversation in values:
            count = len(conversation.messages)
            label = f"{conversation.title}  ·  {count} messages"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, conversation.id)
            self._list.addItem(item)
            if conversation.id == selected_id:
                self._list.setCurrentItem(item)
        if values and self._list.currentItem() is None:
            self._list.setCurrentRow(0)
        if values:
            self._feedback.setText(f"{len(values)} saved conversation(s)")
        else:
            self._feedback.setText("No saved conversations yet.")

    def show_deleted(self) -> None:
        """Give clear feedback after the repository confirms deletion."""
        self._feedback.setText("Conversation deleted.")

    def show_error(self, message: str) -> None:
        """Show a safe repository error without changing saved data."""
        self._feedback.setText(message)

    def _open_selected(self, item: QListWidgetItem | None = None) -> None:
        """Emit the selected conversation ID for opening or resumption."""
        conversation_id = self._selected_id()
        if conversation_id:
            self.open_requested.emit(conversation_id)

    def _delete_selected(self) -> None:
        """Emit the selected ID so the shell can confirm deletion first."""
        conversation_id = self._selected_id()
        if conversation_id:
            self.delete_requested.emit(conversation_id)

    def _selected_id(self) -> str | None:
        """Return the selected stable conversation ID, if one exists."""
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_actions(self) -> None:
        """Enable row actions only while a conversation is selected."""
        selected = self._selected_id() is not None
        self._open.setEnabled(selected)
        self._delete.setEnabled(selected)
