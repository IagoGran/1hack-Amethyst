"""Launch the A3 conversation-history preview with local preview storage."""

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication

from amethyst.ports.persistence import ConversationRepository
from amethyst.ui.a3.preview_repository import PreviewSQLiteConversationRepository
from amethyst.ui.a3.window import A3DesktopWindow


def _database_path() -> Path:
    """Return the app-specific local path used only by this preview."""
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    return Path(location) / "a3-preview-conversations.sqlite3"


def main() -> int:
    """Start the A3 shell with a deterministic fake and preview repository."""
    app = QApplication(sys.argv)
    app.setOrganizationName("Amethyst")
    app.setApplicationName("Amethyst A3 Preview")
    repository: ConversationRepository = PreviewSQLiteConversationRepository(
        _database_path()
    )
    window = A3DesktopWindow(repository)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
