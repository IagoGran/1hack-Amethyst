"""Shared deterministic desktop fixtures."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    """Keep one offscreen Qt event-loop owner alive for desktop checks.

    Parameters
    ----------
    None

    Returns
    -------
    QApplication
        Shared application used by all desktop fixtures.
    """
    application = QApplication.instance() or QApplication([])
    assert isinstance(application, QApplication)
    return application
