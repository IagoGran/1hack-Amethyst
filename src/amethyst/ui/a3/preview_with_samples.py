"""Launch the A3 history preview with fictional conversations preloaded."""

import asyncio
import sys

from PySide6.QtWidgets import QApplication

from amethyst.ports.persistence import ConversationRepository
from amethyst.ui.a3.preview import _database_path
from amethyst.ui.a3.preview_repository import PreviewSQLiteConversationRepository
from amethyst.ui.a3.sample_data import seed_sample_conversations
from amethyst.ui.a3.window import A3DesktopWindow


def main() -> int:
    """Seed sample conversations once, then launch the regular A3 window."""
    app = QApplication(sys.argv)
    app.setOrganizationName("Amethyst")
    app.setApplicationName("Amethyst A3 Preview")
    database_path = _database_path()
    repository: ConversationRepository = PreviewSQLiteConversationRepository(
        database_path
    )
    marker_path = database_path.with_name("a3-samples-seeded")
    asyncio.run(seed_sample_conversations(repository, marker_path))
    window = A3DesktopWindow(repository)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
