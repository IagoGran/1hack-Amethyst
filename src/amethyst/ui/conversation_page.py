"""Persistent conversation transcript and message composer."""

from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Conversation
from amethyst.ui.composer import ComposerPage
from amethyst.ui.message_card import ConversationMessageCard


class ConversationPage(ComposerPage):
    """Show a saved conversation and submit follow-up messages to its ID."""

    composer_placeholder = "Continue this conversation?"
    composer_accessible_name = "Message in current conversation"
    composer_status_name = "Conversation status"

    def __init__(
        self, parent: QWidget | None = None, *, disclosure: str | None = None
    ) -> None:
        """Build the persistent conversation transcript and composer.

        Parameters
        ----------
        parent : QWidget, optional
            Owning widget.
        disclosure : str, optional
            Runtime-specific storage and provider disclosure.

        Returns
        -------
        None
        """
        super().__init__("Chat", parent)
        self._disclosure = disclosure
        self._build_content()

    def _build_content(self) -> None:
        """Arrange local-storage disclosure, transcript, and composer.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        banner = QLabel(
            self._disclosure
            or ("Conversations are stored locally. Responses use the selected model.")
        )
        banner.setObjectName("storageNotice")
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

    def reset(self) -> None:
        """Clear the transcript and prepare a new local conversation.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._clear_messages()
        self._prompt.clear()
        self._status.setText("New conversation")

    def load_conversation(self, conversation: Conversation) -> None:
        """Render ordered saved messages when opening or resuming a conversation.

        Parameters
        ----------
        conversation : Conversation
            Detached conversation snapshot.

        Returns
        -------
        None
        """
        self._clear_messages()
        for message in conversation.messages:
            if message.role == "assistant" and not message.content.strip():
                continue
            role = "user" if message.role == "user" else "assistant"
            self._add_message(role, message.content)
        self._status.setText(conversation.title)
        self._scroll_to_latest()

    def begin_turn(self, prompt: str) -> None:
        """Show the submitted prompt and mark the model response as running.

        Parameters
        ----------
        prompt : str
            User request used by the operation.

        Returns
        -------
        None
        """
        self._add_message("user", prompt)
        self._active_response = self._add_message("assistant", "")
        self._prompt.clear()
        self._prompt.setEnabled(False)
        self._send.setEnabled(False)
        self._status.setText("Running · saving conversation")

    def append_delta(self, text: str) -> None:
        """Append one streamed assistant fragment to the transcript.

        Parameters
        ----------
        text : str
            Text fragment to inspect, redact, or display.

        Returns
        -------
        None
        """
        if self._active_response is not None:
            self._active_response.append_text(text)
        self._scroll_to_latest()

    def finish_turn(self, status: str = "Saved") -> None:
        """Restore composer input and indicate that the turn was saved.

        Parameters
        ----------
        status : str
            Visible task or diagnostic status.

        Returns
        -------
        None
        """
        self._discard_empty_response()
        self._prompt.setEnabled(True)
        self._send.setEnabled(True)
        self._status.setText(status)
        self._prompt.setFocus()

    def _discard_empty_response(self) -> None:
        """Remove the streamed assistant placeholder if no text was produced.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        response = self._active_response
        if response is None or not response.is_empty():
            return
        self._message_layout.removeWidget(response)
        self._message_cards.remove(response)
        response.deleteLater()
        self._active_response = None

    def show_error(self, message: str) -> None:
        """Show a safe operation failure and return the composer to idle.

        Parameters
        ----------
        message : str
            Display-safe text associated with the operation.

        Returns
        -------
        None
        """
        self._add_message("error", f"Unable to complete request: {message}")
        self.finish_turn("Failed")

    def _add_message(self, role: str, content: str) -> ConversationMessageCard:
        """Insert one role-styled card before the transcript's bottom spacer.

        Parameters
        ----------
        role : str
            Conversation message role.
        content : str
            Text content to display, persist, or return.

        Returns
        -------
        ConversationMessageCard
            Value produced by the operation.
        """
        card = ConversationMessageCard(role, content)
        self._message_layout.insertWidget(self._message_layout.count() - 1, card)
        self._message_cards.append(card)
        return card

    def _clear_messages(self) -> None:
        """Remove transcript cards and reset the active streamed response.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for card in self._message_cards:
            self._message_layout.removeWidget(card)
            card.deleteLater()
        self._message_cards.clear()
        self._active_response = None

    def _scroll_to_latest(self) -> None:
        """Keep the newest message card visible after loads and stream updates.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
