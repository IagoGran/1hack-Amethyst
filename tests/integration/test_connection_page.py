"""Exercise category-isolated settings forms without external services."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from amethyst.domain.contracts import Connection
from amethyst.ui.connection_page import ConnectionPage


@pytest.fixture
def page(qt_app: QApplication) -> Iterator[ConnectionPage]:
    """Create a disposable settings page on the shared Qt application.

    Parameters
    ----------
    qt_app : QApplication
        Shared headless Qt event-loop owner.

    Yields
    ------
    ConnectionPage
        Independent model and tool editors populated with saved settings.
    """
    widget = ConnectionPage()
    widget.refresh(
        (
            Connection("local", "ollama", {"model_id": "fixture"}),
            Connection("data", "sqlite", {"database": "fixture.sqlite3"}),
        )
    )
    yield widget
    widget.close()
    widget.deleteLater()
    qt_app.processEvents()


def test_forms_keep_models_and_tools_separate(page: ConnectionPage) -> None:
    """Keep saved records, type choices, and option widgets in their category.

    Parameters
    ----------
    page : ConnectionPage
        Populated settings tabs.

    Returns
    -------
    None
    """
    assert [page.tabText(i) for i in range(page.count())] == ["Models", "Tools"]
    assert set(page.models.records) == {"local"}
    assert set(page.tools.records) == {"data"}
    assert {page.models.kind.itemText(i) for i in range(page.models.kind.count())} == {
        "openai",
        "gemini",
        "deepseek",
        "ollama",
    }
    assert "database" not in page.models.fields
    assert "model_id" not in page.tools.fields
    page.models.load("local")
    page.tools.load("data")
    assert page.models.fields["model_id"].text() == "fixture"
    assert page.tools.fields["database"].text() == "fixture.sqlite3"


def test_save_preserves_reference_and_separates_secret(page: ConnectionPage) -> None:
    """Emit typed options and replacement secrets through separate channels.

    Parameters
    ----------
    page : ConnectionPage
        Populated settings tabs.

    Returns
    -------
    None
    """
    saved = Connection(
        "remote", "openai", {"model_id": "fixture"}, credential_ref="stored-key"
    )
    page.refresh((saved,))
    commands: list[tuple[str, object]] = []
    page.command.connect(lambda action, payload: commands.append((action, payload)))
    page.models.load("remote")
    page.models.fields["context_tokens"].setText("8192")
    page.models.secret.setText("replacement-fixture")
    page.models.save()
    action, payload = commands.pop()
    assert action == "save_connection"
    assert isinstance(payload, tuple)
    record, secret = payload
    assert record.options == {"model_id": "fixture", "context_tokens": 8192}
    assert record.credential_ref == "stored-key"
    assert secret == "replacement-fixture"
    assert page.models.secret.text() == ""
    assert page.notice is page.models.notice


def test_other_category_name_cannot_be_overwritten(page: ConnectionPage) -> None:
    """Prevent a tool form from overwriting a saved model with the same ID.

    Parameters
    ----------
    page : ConnectionPage
        Populated settings tabs.

    Returns
    -------
    None
    """
    commands: list[tuple[str, object]] = []
    page.command.connect(lambda action, payload: commands.append((action, payload)))
    page.tools.identifier.setText("local")
    page.tools.fields["database"].setText("fixture.sqlite3")
    page.tools.save()
    assert commands == []
    assert "other connection category" in page.tools.notice.text()
    page.tools.identifier.setText("new-data")
    page.tools.save()
    assert commands[0][0] == "save_connection"
    assert page.notice is page.tools.notice
