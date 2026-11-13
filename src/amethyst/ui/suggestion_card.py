"""Clickable prompt suggestion used on the empty chat screen."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton

from amethyst.ui.base_card import BaseCard


class SuggestionCard(BaseCard):
    """Show a suggested task and emit its text when selected."""

    prompt_selected = Signal(str)

    def __init__(self, title: str, description: str, prompt: str) -> None:
        """Build a labeled prompt card and retain the prompt payload."""
        super().__init__()
        self.setObjectName("suggestion")
        self._prompt = prompt
        heading = QLabel(f"✦   {title}")
        heading.setStyleSheet("font-weight: 650; color: #e5e1eb;")
        detail = QLabel(description)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        button = QPushButton("Use suggestion")
        button.setObjectName("suggestionButton")
        button.setAccessibleName(f"Use suggestion: {title}")
        button.clicked.connect(self._select_prompt)
        self.content_layout.addWidget(heading)
        self.content_layout.addWidget(detail, 1)
        self.content_layout.addWidget(button)

    def _select_prompt(self) -> None:
        """Publish the stored prompt for the chat composer."""
        self.prompt_selected.emit(self._prompt)
