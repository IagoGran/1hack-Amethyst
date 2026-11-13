"""Launch the explicitly fake, in-memory A1 desktop preview."""

import sys

from PySide6.QtWidgets import QApplication

from amethyst.adapters.fakes import FakeApplicationService
from amethyst.ui.window import DesktopWindow


def main() -> int:
    """Start the desktop shell with deterministic S0 fake responses."""
    app = QApplication(sys.argv)
    app.setApplicationName("Amethyst desktop preview")
    service = FakeApplicationService(
        chunks=(
            "This response comes from the S0 development fake. ",
            "No model, tools, local files, or persistence are used.",
        )
    )
    window = DesktopWindow(service)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
