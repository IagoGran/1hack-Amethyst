"""Compact role-styled message cards for conversation transcripts."""

from datetime import datetime
from math import ceil
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class ConversationMessageCard(QFrame):
    """Display one user or assistant message with role-specific styling."""

    def __init__(
        self,
        role: str,
        content: str = "",
        parent: QWidget | None = None,
        *,
        created_at: str | None = None,
        stacktrace: tuple[str, ...] = (),
    ) -> None:
        """Build a selectable message block using the role's visual treatment.

        Parameters
        ----------
        role : str
            Conversation message role.
        content : str
            Text content to display, persist, or return.
        parent : QWidget | None
            Owning widget, descriptor, or temporary-data directory.
        created_at : str or None
            UTC timestamp displayed in local time.
        stacktrace : tuple of str
            Safe frame locations shown in expandable error details.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self._role = role
        self._raw_content = content
        self._action_callback: Callable[[], None] | None = None
        self._action_button: QPushButton | None = None
        self._thinking_frame = 0
        self._content = QTextBrowser()
        self._content.setMarkdown(content)
        self._build_content(created_at, stacktrace)
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(350)
        self._thinking_timer.timeout.connect(self._animate_thinking)
        self._content.document().documentLayout().documentSizeChanged.connect(
            self._fit_content_height
        )
        self._fit_content_height()

    def _build_content(
        self, created_at: str | None, stacktrace: tuple[str, ...]
    ) -> None:
        """Add a role label and wrapped, selectable message text.

        Parameters
        ----------
        created_at : str or None
            Stored UTC timestamp shown in local time.
        stacktrace : tuple of str
            Safe frame locations for an expandable error card.

        Returns
        -------
        None
        """
        assistant = self._role == "assistant"
        error = self._role == "error"
        notice = self._role == "notice"
        object_name = "assistantResponse" if assistant else "userMessage"
        accessible_name = "Assistant response" if assistant else "User message"
        if error:
            object_name = "errorMessage"
            accessible_name = "Task error"
        elif notice:
            object_name = "systemMessage"
            accessible_name = "Conversation notice"
        self.setObjectName(object_name)
        self.setAccessibleName(accessible_name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        heading_text = "AMETHYST" if assistant else "YOU"
        heading_name = "assistantRole" if assistant else "userRole"
        if error:
            heading_text = "NOTICE"
            heading_name = "errorRole"
        elif notice:
            heading_text = "MODEL"
            heading_name = "userRole"
        heading = QLabel(heading_text)
        heading.setObjectName(heading_name)
        layout.addWidget(heading)
        timestamp = QLabel(self._format_timestamp(created_at))
        timestamp.setObjectName("messageTimestamp")
        timestamp.setVisible(bool(created_at))
        layout.addWidget(timestamp)
        content_name = "assistantContent" if assistant else "userContent"
        if notice:
            content_name = "systemContent"
        self._content.setObjectName(content_name)
        if error:
            self._content.setObjectName("errorContent")
        self._content.setOpenExternalLinks(False)
        self._content.setFrameShape(QFrame.Shape.NoFrame)
        self._content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._content.setSizeAdjustPolicy(
            QTextBrowser.SizeAdjustPolicy.AdjustToContents
        )
        self._content.setMinimumHeight(28)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._content)
        self._thinking = QLabel("Thinking")
        self._thinking.setObjectName("thinkingIndicator")
        self._thinking.setVisible(False)
        if assistant:
            layout.addWidget(self._thinking)
        if error and stacktrace:
            details = QPlainTextEdit("\n".join(stacktrace))
            details.setReadOnly(True)
            details.setMaximumHeight(150)
            details.setVisible(False)
            toggle = QPushButton("Show technical details")
            toggle.setCheckable(True)
            toggle.toggled.connect(details.setVisible)
            layout.addWidget(toggle)
            layout.addWidget(details)

    def append_text(self, text: str) -> None:
        """Append one streamed fragment and refresh the wrapped text label.

        Parameters
        ----------
        text : str
            Text fragment to inspect, redact, or display.

        Returns
        -------
        None
        """
        self._raw_content += text
        self._content.setMarkdown(self._raw_content)
        if text.strip():
            self.set_thinking(False)
        self._fit_content_height()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Recalculate wrapped Markdown height whenever the card width changes.

        Parameters
        ----------
        event : QResizeEvent
            Widget resize event.

        Returns
        -------
        None
        """
        super().resizeEvent(event)
        width = max(1, self._content.viewport().width())
        self._content.document().setTextWidth(width)
        QTimer.singleShot(0, self._fit_content_height)

    def _fit_content_height(self, *_args: object) -> None:
        """Size the Markdown browser to its wrapped document, without inner scroll.

        Returns
        -------
        None
        """
        width = max(1, self._content.viewport().width())
        document = self._content.document()
        document.setTextWidth(width)
        height = ceil(document.documentLayout().documentSize().height()) + 4
        self._content.setFixedHeight(max(28, height))
        host = self.parentWidget()
        if host and host.layout():
            host.layout().invalidate()
            host.updateGeometry()

    def set_thinking(self, active: bool) -> None:
        """Start or stop the animated status shown inside an assistant bubble.

        Parameters
        ----------
        active : bool
            Whether the model is waiting to emit its first text fragment.

        Returns
        -------
        None
        """
        if self._role != "assistant":
            return
        if active:
            self._thinking_frame = 0
            self._thinking.setText("Thinking")
            self._thinking.show()
            self._thinking_timer.start()
        else:
            self._thinking_timer.stop()
            self._thinking.hide()

    def _animate_thinking(self) -> None:
        """Advance the thinking indicator's animated ellipsis.

        Returns
        -------
        None
        """
        self._thinking_frame = (self._thinking_frame + 1) % 4
        self._thinking.setText("Thinking" + "." * self._thinking_frame)

    def set_action_button(
        self, label: str | None, callback: Callable[[], None] | None = None
    ) -> None:
        """Show or remove a contextual action inside this message card.

        Parameters
        ----------
        label : str or None
            Visible button text, or ``None`` to hide the action.
        callback : callable or None
            Action invoked when the button is pressed.

        Returns
        -------
        None
        """
        if label is None or callback is None or self._role != "assistant":
            self._action_callback = None
            if self._action_button:
                self._action_button.hide()
            return
        self._action_callback = callback
        if self._action_button is None:
            self._action_button = QPushButton()
            self._action_button.setObjectName("messageAction")
            self._action_button.clicked.connect(self._invoke_action)
            self.layout().addWidget(self._action_button)
        self._action_button.setText(label)
        self._action_button.setAccessibleName(label)
        self._action_button.show()

    def _invoke_action(self) -> None:
        """Invoke the currently assigned message action, if available.

        Returns
        -------
        None
        """
        if self._action_callback:
            self._action_callback()

    def is_empty(self) -> bool:
        """Return whether the message card has received any visible content.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            True when the card contains no text.
        """
        return not self._raw_content.strip()

    @property
    def role(self) -> str:
        """Return the role represented by this transcript card.

        Returns
        -------
        str
            Message role used by transcript action placement.
        """
        return self._role

    @staticmethod
    def _format_timestamp(value: str | None) -> str:
        """Format a stored UTC timestamp in the user's local timezone.

        Parameters
        ----------
        value : str or None
            ISO timestamp stored with the message.

        Returns
        -------
        str
            Localized short timestamp or an empty string for legacy messages.
        """
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return ""
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y-%m-%d %H:%M")
