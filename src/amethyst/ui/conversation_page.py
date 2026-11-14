"""Persistent conversation transcript and message composer."""

from datetime import datetime, timezone

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Signal, QTimer
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Conversation
from amethyst.ui.composer import ComposerPage
from amethyst.ui.message_card import ConversationMessageCard


class ConversationPage(ComposerPage):
    """Show a saved conversation and submit follow-up messages to its ID."""

    workspace_requested = Signal()
    workspace_access_requested = Signal(bool)
    undo_requested = Signal()

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
        self.workspace_root: str | None = None
        self.workspace_granted = False
        self._animations: list[QPropertyAnimation] = []
        self._activity_text = "Thinking"
        self._activity_frame = 0
        self._build_content()
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(350)
        self._activity_timer.timeout.connect(self._animate_activity)

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
        workspace_row = QHBoxLayout()
        self.workspace_label = QLabel("Workspace: none selected")
        self.workspace_label.setObjectName("storageNotice")
        self.workspace_label.setWordWrap(True)
        workspace_row.addWidget(self.workspace_label, 1)
        choose_workspace = QPushButton("Choose workspace")
        choose_workspace.clicked.connect(self.workspace_requested.emit)
        workspace_row.addWidget(choose_workspace)
        self.workspace_access = QPushButton("Allow reads")
        self.workspace_access.clicked.connect(self._toggle_workspace_access)
        workspace_row.addWidget(self.workspace_access)
        self.undo_button = QPushButton("Review undo")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_requested.emit)
        workspace_row.addWidget(self.undo_button)
        self.content_layout.addLayout(workspace_row)
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
        self.set_workspace(None, False)
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
        timeline = [
            (message.created_at, "message", message)
            for message in conversation.messages
        ]
        timeline.extend(
            (action.created_at, "model", action)
            for action in conversation.action_history
            if action.tool == "model.selection"
        )
        for timestamp, kind, item in sorted(timeline, key=lambda entry: entry[0]):
            if kind == "model":
                self._add_message("notice", item.summary, timestamp)
                continue
            if item.role == "assistant" and not item.content.strip():
                continue
            role = "user" if item.role == "user" else "assistant"
            self._add_message(role, item.content, timestamp)
        self.set_workspace(
            conversation.workspace_root,
            conversation.workspace_read_granted,
            len(conversation.undo_records),
        )
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
        self._activity_text = "Thinking"
        self._activity_timer.start()
        self._scroll_to_latest()

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
        self._activity_timer.stop()
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

    def show_error(
        self, message: str, stacktrace: tuple[str, ...] = ()
    ) -> None:
        """Show a safe operation failure and return the composer to idle.

        Parameters
        ----------
        message : str
            Display-safe text associated with the operation.
        stacktrace : tuple of str
            Sanitized frame locations without source or exception arguments.

        Returns
        -------
        None
        """
        self._add_message(
            "error", f"Unable to complete request: {message}", stacktrace=stacktrace
        )
        self.finish_turn("Failed")

    def _add_message(
        self,
        role: str,
        content: str,
        created_at: str | None = None,
        stacktrace: tuple[str, ...] = (),
    ) -> ConversationMessageCard:
        """Insert one role-styled card before the transcript's bottom spacer.

        Parameters
        ----------
        role : str
            Conversation message role.
        content : str
            Text content to display, persist, or return.
        created_at : str or None
            Timestamp associated with a saved message, if available.
        stacktrace : tuple of str
            Safe frame locations for an error card.

        Returns
        -------
        ConversationMessageCard
            Value produced by the operation.
        """
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        card = ConversationMessageCard(
            role, content, created_at=timestamp, stacktrace=stacktrace
        )
        self._message_layout.insertWidget(self._message_layout.count() - 1, card)
        self._message_cards.append(card)
        if role == "assistant":
            effect = QGraphicsOpacityEffect(card)
            card.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(220)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.finished.connect(lambda: self._animations.remove(animation))
            self._animations.append(animation)
            animation.start()
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
        QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum()))

    def set_workspace(
        self, root: str | None, granted: bool, undo_count: int = 0
    ) -> None:
        """Display the selected chat's root and its persisted read grant.

        Parameters
        ----------
        root : str or None
            Absolute directory associated with the current conversation.
        granted : bool
            Whether this chat currently allows workspace reads.
        undo_count : int
            Number of retained file snapshots available for review.

        Returns
        -------
        None
        """
        self.workspace_root = root
        self.workspace_granted = granted and bool(root)
        self.workspace_label.setText(f"Workspace: {root or 'none selected'}")
        self.workspace_access.setText(
            "Revoke reads" if self.workspace_granted else "Allow reads"
        )
        self.workspace_access.setEnabled(bool(root))
        self.undo_button.setEnabled(bool(root and granted and undo_count))
        self.undo_button.setText(f"Review undo ({undo_count})")

    def _toggle_workspace_access(self) -> None:
        """Request the inverse chat-scoped workspace read permission state.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.workspace_access_requested.emit(not self.workspace_granted)

    def set_activity(self, activity: str) -> None:
        """Show the current task phase in the conversation status pill.

        Parameters
        ----------
        activity : str
            Current execution phase or terminal label.

        Returns
        -------
        None
        """
        self._status.setText(activity)
        self._activity_text = activity

    def add_notice(self, text: str) -> None:
        """Add a non-model system marker to the visible conversation timeline.

        Parameters
        ----------
        text : str
            User-visible status marker such as a model switch.

        Returns
        -------
        None
        """
        self._add_message("notice", text)
        self._scroll_to_latest()

    def _animate_activity(self) -> None:
        """Animate a small thinking indicator while a turn is active.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._activity_frame = (self._activity_frame + 1) % 4
        self._status.setText(self._activity_text + "." * self._activity_frame)
