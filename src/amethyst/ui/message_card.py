"""Compact role-styled message cards for conversation transcripts."""

from datetime import datetime

from PySide6.QtCore import Qt
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
        self._content = QTextBrowser()
        self._content.setMarkdown(content)
        self._build_content(created_at, stacktrace)

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
        self._content.setMinimumHeight(24)
        self._content.setMaximumHeight(1200)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._content)
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
