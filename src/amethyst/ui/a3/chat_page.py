"""Conversation transcript and composer for the A3 preview."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Conversation
from amethyst.ui.base_page import BasePage
from amethyst.ui.a3.message_card import ConversationMessageCard


class A3ChatPage(BasePage):
    """Show a saved conversation and submit follow-up messages to its ID."""

    message_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the persistent conversation transcript and composer."""
        super().__init__("Chat", parent)
        self._build_content()

    def _build_content(self) -> None:
        """Arrange local-storage disclosure, transcript, and composer."""
        banner = QLabel(
            "A3 HISTORY PREVIEW · Fake responses · Conversations stored locally "
            "in a preview database"
        )
        banner.setObjectName("demoBanner")
        banner.setWordWrap(True)
        self.content_layout.addWidget(banner)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._message_host = QWidget()
        self._message_layout = QVBoxLayout(self._message_host)
        self._message_layout.setContentsMargins(8, 8, 8, 8)
        self._message_layout.setSpacing(12)
        self._message_host.setObjectName("messageHost")
        self._message_cards: list[ConversationMessageCard] = []
        self._active_response: ConversationMessageCard | None = None
        self._message_layout.addStretch(1)
        self._scroll.setWidget(self._message_host)
        self.content_layout.addWidget(self._scroll, 1)
        self._build_composer()

    def _build_composer(self) -> None:
        """Create a keyboard-friendly prompt field and send control."""
        row = QHBoxLayout()
        self._prompt = QLineEdit()
        self._prompt.setObjectName("prompt")
        self._prompt.setPlaceholderText("Continue this conversation…")
        self._prompt.setAccessibleName("Message in current conversation")
        self._prompt.returnPressed.connect(self._submit)
        row.addWidget(self._prompt, 1)
        self._status = QLabel("Ready")
        self._status.setObjectName("statusPill")
        self._status.setAccessibleName("Conversation status")
        row.addWidget(self._status)
        self._send = QPushButton("Send ↑")
        self._send.setObjectName("send")
        self._send.clicked.connect(self._submit)
        row.addWidget(self._send)
        self.content_layout.addLayout(row)

    def _submit(self) -> None:
        """Send a non-empty prompt when no previous turn is still running."""
        prompt = self._prompt.text().strip()
        if prompt and self._send.isEnabled():
            self.message_submitted.emit(prompt)

    def reset(self) -> None:
        """Clear the transcript and prepare a new local conversation."""
        self._clear_messages()
        self._prompt.clear()
        self._status.setText("New conversation")

    def load_conversation(self, conversation: Conversation) -> None:
        """Render ordered saved messages when opening or resuming a conversation."""
        self._clear_messages()
        for message in conversation.messages:
            role = "user" if message.role == "user" else "assistant"
            self._add_message(role, message.content)
        self._status.setText(conversation.title)
        self._scroll_to_latest()

    def begin_turn(self, prompt: str) -> None:
        """Show the submitted user prompt and mark the fake response as running."""
        self._add_message("user", prompt)
        self._active_response = self._add_message("assistant", "")
        self._prompt.clear()
        self._prompt.setEnabled(False)
        self._send.setEnabled(False)
        self._status.setText("Running · saving conversation")

    def append_delta(self, text: str) -> None:
        """Append one streamed assistant fragment to the transcript."""
        if self._active_response is not None:
            self._active_response.append_text(text)
        self._scroll_to_latest()

    def finish_turn(self, status: str = "Saved") -> None:
        """Restore composer input and indicate that the turn was saved."""
        self._prompt.setEnabled(True)
        self._send.setEnabled(True)
        self._status.setText(status)
        self._prompt.setFocus()

    def show_error(self, message: str) -> None:
        """Show a safe operation failure and return the composer to idle."""
        self._add_message("error", f"Unable to complete request: {message}")
        self.finish_turn("Failed")

    def _add_message(self, role: str, content: str) -> ConversationMessageCard:
        """Insert one role-styled card before the transcript's bottom spacer."""
        card = ConversationMessageCard(role, content)
        self._message_layout.insertWidget(self._message_layout.count() - 1, card)
        self._message_cards.append(card)
        return card

    def _clear_messages(self) -> None:
        """Remove transcript cards and reset the active streamed response."""
        for card in self._message_cards:
            self._message_layout.removeWidget(card)
            card.deleteLater()
        self._message_cards.clear()
        self._active_response = None

    def _scroll_to_latest(self) -> None:
        """Keep the newest message card visible after loads and stream updates."""
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
