"""Accessible message entry and shared chat page controls."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from amethyst.ui.base_page import BasePage


class ChatComposer(QFrame):
    """Own prompt validation, keyboard submission, status, and send controls."""

    submitted = Signal(str)

    def __init__(
        self,
        placeholder: str,
        accessible_name: str,
        *,
        status_name: str = "Task status",
    ) -> None:
        """Build a keyboard-accessible horizontal message composer.

        Parameters
        ----------
        placeholder : str
            Empty prompt guidance.
        accessible_name : str
            Screen reader label for message entry.
        status_name : str
            Screen reader label for the visible status.

        Returns
        -------
        None
        """
        super().__init__()
        self.prompt = QLineEdit()
        self.prompt.setObjectName("prompt")
        self.prompt.setPlaceholderText(placeholder)
        self.prompt.setAccessibleName(accessible_name)
        self.status = QLabel("Ready")
        self.status.setObjectName("statusPill")
        self.status.setAccessibleName(status_name)
        self.send = QPushButton("Send ↑")
        self.send.setObjectName("send")
        self.send.setAccessibleName("Send message")
        actions = QHBoxLayout(self)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.prompt, 1)
        actions.addWidget(self.status)
        actions.addWidget(self.send)
        self.prompt.returnPressed.connect(self.submit)
        self.send.clicked.connect(self.submit)

    def submit(self) -> None:
        """Emit a trimmed nonempty prompt only while sending is enabled.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        prompt = self.prompt.text().strip()
        if prompt and self.send.isEnabled():
            self.submitted.emit(prompt)


class ComposerPage(BasePage):
    """Share composer construction while pages retain their transcript behavior."""

    message_submitted = Signal(str)
    composer_placeholder = "Message Amethyst…"
    composer_accessible_name = "Message Amethyst"
    composer_status_name = "Task status"

    def _build_composer(self) -> None:
        """Attach shared controls and preserve the existing page control aliases.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._composer = ChatComposer(
            self.composer_placeholder,
            self.composer_accessible_name,
            status_name=self.composer_status_name,
        )
        self._prompt = self._composer.prompt
        self._status = self._composer.status
        self._send = self._composer.send
        self._composer.submitted.connect(self._forward_prompt)
        self.content_layout.addWidget(self._composer)

    def _forward_prompt(self, prompt: str) -> None:
        """Forward validated text through the page's existing submission signal.

        Parameters
        ----------
        prompt : str
            Trimmed nonempty message.

        Returns
        -------
        None
        """
        self.message_submitted.emit(prompt)
