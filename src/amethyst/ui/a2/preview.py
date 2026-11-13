"""Launch the interactive A2 preview with controllable fake task scenarios."""

import sys

from PySide6.QtWidgets import QApplication

from amethyst.ui.a2.preview_service import A2PreviewService
from amethyst.ui.a2.window import A2DesktopWindow


def main() -> int:
    """Start the A2 shell with its in-memory demonstration service."""
    app = QApplication(sys.argv)
    app.setApplicationName("Amethyst A2 preview")
    window = A2DesktopWindow(A2PreviewService())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
