"""Base class for pages displayed inside the desktop shell."""

from PySide6.QtWidgets import QVBoxLayout, QWidget


class BasePage(QWidget):
    """Provide a shared page layout and title for desktop screens."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        """Initialize the page container with common layout defaults.

        Parameters
        ----------
        title : str
            Human-readable conversation or page title.
        parent : QWidget | None
            Owning widget, descriptor, or temporary-data directory.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self.title = title
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(0, 18, 0, 0)
        self.content_layout.setSpacing(16)
