"""Standalone desktop entry point and explicit runtime configuration."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Launch the integrated desktop with optional workspace/sandbox settings.

    Parameters
    ----------
    None

    Returns
    -------
    None

    Notes
    -----
    Sandbox execution remains disabled unless a validated host and pinned image
    are explicitly configured. No credentials are accepted as CLI arguments.
    """
    parser = argparse.ArgumentParser(description="Amethyst local coding desktop")
    parser.add_argument("--version", action="version", version="1hack-amethyst 0.1.0")
    parser.add_argument("--database", type=Path, help="Application SQLite database")
    parser.add_argument(
        "--workspace", type=Path, help="Workspace boundary (no read grant implied)"
    )
    parser.add_argument(
        "--sandbox-image", help="Pre-provisioned image pinned by SHA-256 digest"
    )
    parser.add_argument(
        "--enable-sandbox",
        action="store_true",
        help="Enable Docker after completing documented host validation",
    )
    args = parser.parse_args()
    if args.enable_sandbox and not (args.sandbox_image and args.workspace):
        parser.error("--enable-sandbox requires --workspace and --sandbox-image")
    from PySide6.QtWidgets import QApplication

    from amethyst.ui.desktop import DesktopWindow
    from amethyst.ui.desktop_worker import DesktopWorker

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Amethyst")
    worker = DesktopWorker(
        args.database,
        workspace=args.workspace,
        sandbox_image=args.sandbox_image,
        enable_sandbox=args.enable_sandbox,
    )
    window = DesktopWindow(worker)
    window.show()
    app.exec()
