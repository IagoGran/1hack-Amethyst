"""Placeholder screen for the other A1 navigation destinations."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from amethyst.ui.base_page import BasePage


class PlaceholderPage(BasePage):
    """Describe an unfinished screen without implying it is implemented."""

    def __init__(
        self, title: str, description: str, parent: QWidget | None = None
    ) -> None:
        """Create a named placeholder with an explicit preview disclaimer."""
        super().__init__(title, parent)
        self._description = description
        self._build_content()

    def _build_content(self) -> None:
        """Center a card with the screen description and preview state."""
        self.content_layout.addStretch(1)
        card = QFrame()
        card.setObjectName("placeholderCard")
        card.setMaximumWidth(640)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        heading = QLabel(self.title)
        heading.setObjectName("pageTitle")
        description = QLabel(self._description)
        description.setObjectName("muted")
        description.setWordWrap(True)
        note = QLabel("This screen is a layout placeholder in the A1 preview.")
        note.setObjectName("demoBanner")
        note.setWordWrap(True)
        card_layout.addWidget(heading)
        card_layout.addWidget(description)
        card_layout.addWidget(note)
        self.content_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addStretch(1)
