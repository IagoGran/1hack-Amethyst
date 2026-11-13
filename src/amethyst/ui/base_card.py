"""Reusable card container for small desktop-preview surfaces."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class BaseCard(QFrame):
    """Provide shared visual treatment and layout for preview cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create a framed card with the shared preview style."""
        super().__init__(parent)
        self.setObjectName("placeholderCard")
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(18, 16, 18, 16)
        self.content_layout.setSpacing(10)
