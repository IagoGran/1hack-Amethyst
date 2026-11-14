"""Compact role-styled message cards for conversation transcripts."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class ConversationMessageCard(QFrame):
    """Display one user or assistant message with role-specific styling."""

    def __init__(
        self, role: str, content: str = "", parent: QWidget | None = None
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

        Returns
        -------
        None
        """
        super().__init__(parent)
        self._role = role
        self._content = QLabel(content)
        self._build_content()

    def _build_content(self) -> None:
        """Add a role label and wrapped, selectable message text.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        assistant = self._role == "assistant"
        error = self._role == "error"
        object_name = "assistantResponse" if assistant else "userMessage"
        accessible_name = "Assistant response" if assistant else "User message"
        if error:
            object_name = "errorMessage"
            accessible_name = "Task error"
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
        heading = QLabel(heading_text)
        heading.setObjectName(heading_name)
        layout.addWidget(heading)
        self._content.setObjectName("assistantContent" if assistant else "userContent")
        if error:
            self._content.setObjectName("errorContent")
        self._content.setTextFormat(Qt.TextFormat.PlainText)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._content)

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
        self._content.setText(self._content.text() + text)

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
        return not self._content.text().strip()
