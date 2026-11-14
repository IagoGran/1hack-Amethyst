"""Separate model and tool settings built on a shared connection editor."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from amethyst.configuration.catalog import (
    CONNECTION_SPECS,
    NUMERIC_FIELDS,
    ConnectionCategory,
    ConnectionKind,
)
from amethyst.domain.contracts import Connection, JsonValue

FIELDS = {kind.value: spec.fields for kind, spec in CONNECTION_SPECS.items()}


class ConnectionEditor(QWidget):
    """Edit persisted connections without displaying stored credential values."""

    command = Signal(str, object)

    def __init__(self, category: ConnectionCategory) -> None:
        """Build type-specific settings and masked replacement-secret controls.

        Parameters
        ----------
        category : ConnectionCategory
            Restrict visible records and types to models or tools.

        Returns
        -------
        None
        """
        super().__init__()
        layout = QVBoxLayout(self)
        self.category = category
        self._all_records: dict[str, Connection] = {}
        layout.addWidget(
            QLabel("Models" if category == ConnectionCategory.MODEL else "Tools")
        )
        self.records: dict[str, Connection] = {}
        self.items = QListWidget()
        self.items.currentTextChanged.connect(self.load)
        layout.addWidget(self.items)
        form = QFormLayout()
        self.identifier = QLineEdit()
        self.kind = QComboBox()
        self.kind.addItems(
            [
                kind.value
                for kind, spec in CONNECTION_SPECS.items()
                if spec.category == category
            ]
        )
        self.kind.currentTextChanged.connect(self._show_fields)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(True)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText("Blank keeps the existing credential")
        form.addRow("Connection name", self.identifier)
        form.addRow("Type", self.kind)
        form.addRow(self.enabled)
        self.fields: dict[str, QLineEdit] = {}
        keys = dict.fromkeys(
            key
            for kind, spec in CONNECTION_SPECS.items()
            if spec.category == category
            for key in spec.fields
        )
        for key in keys:
            field = QLineEdit()
            field.setAccessibleName(key.replace("_", " "))
            self.fields[key] = field
            form.addRow(key.replace("_", " ").title(), field)
        form.addRow("API key / password", self.secret)
        self.form = form
        layout.addLayout(form)
        row = QHBoxLayout()
        for title, handler in (
            ("New", self.clear),
            ("Save", self.save),
            ("Test", self.test),
            ("Delete", self.delete),
        ):
            button = QPushButton(title)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        self.notice = QLabel("Credentials use the OS store, or memory until exit.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self._show_fields(self.kind.currentText())

    def _show_fields(self, kind: str) -> None:
        """Show only options accepted by the chosen adapter.

        Parameters
        ----------
        kind : str
            Connection type.

        Returns
        -------
        None
        """
        if not hasattr(self, "form"):
            return
        for key, field in self.fields.items():
            self.form.setRowVisible(field, key in FIELDS[kind])

    def refresh(self, records: tuple[Connection, ...]) -> None:
        """Refresh connection names without overwriting an unfinished form.

        Parameters
        ----------
        records : tuple of Connection
            Detached persisted settings.

        Returns
        -------
        None
        """
        self._all_records = {record.id: record for record in records}
        self.records = {
            record.id: record
            for record in records
            if record.kind in CONNECTION_SPECS
            and CONNECTION_SPECS[ConnectionKind(record.kind)].category == self.category
        }
        self.items.blockSignals(True)
        self.items.clear()
        self.items.addItems(list(self.records))
        self.items.blockSignals(False)

    def load(self, identifier: str) -> None:
        """Load secret-free options for a selected connection.

        Parameters
        ----------
        identifier : str
            Selected persistent ID.

        Returns
        -------
        None
        """
        record = self.records.get(identifier)
        if record is None:
            return
        self.identifier.setText(record.id)
        self.kind.setCurrentText(record.kind)
        self.enabled.setChecked(record.enabled)
        self.secret.clear()
        for key, field in self.fields.items():
            field.setText(str(record.options.get(key, "")))

    def clear(self) -> None:
        """Prepare a new connection form.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.identifier.clear()
        self.secret.clear()
        self.enabled.setChecked(True)
        for field in self.fields.values():
            field.clear()

    def save(self) -> None:
        """Submit validated scalar settings and a separate replacement secret.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        identifier = self.identifier.text().strip()
        if not identifier:
            self.notice.setText("Enter a connection name.")
            return
        options: dict[str, JsonValue] = {}
        try:
            for key in FIELDS[self.kind.currentText()]:
                value = self.fields[key].text().strip()
                if value:
                    options[key] = int(value) if key in NUMERIC_FIELDS else value
        except ValueError:
            self.notice.setText("Enter a whole number for numeric settings.")
            return
        if identifier in self._all_records and identifier not in self.records:
            self.notice.setText("This name belongs to the other connection category.")
            return
        previous = self.records.get(identifier)
        reference = previous.credential_ref if previous else None
        record = Connection(
            identifier,
            self.kind.currentText(),
            options,
            self.enabled.isChecked(),
            reference,
        )
        self.command.emit("save_connection", (record, self.secret.text()))
        self.secret.clear()

    def test(self) -> None:
        """Test the saved connection selected in the form.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.notice.setText("Testing saved connection...")
        self.command.emit("test_connection", self.identifier.text().strip())

    def delete(self) -> None:
        """Delete the connection settings selected in the form.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.command.emit("delete_connection", self.identifier.text().strip())


class ModelConnectionPage(ConnectionEditor):
    """Configure only model providers and their generation settings."""

    def __init__(self) -> None:
        """Build the model editor using shared connection controls.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__(ConnectionCategory.MODEL)


class ToolConnectionPage(ConnectionEditor):
    """Configure only SQL, search, and retrieval resources."""

    def __init__(self) -> None:
        """Build the tool editor using shared connection controls.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__(ConnectionCategory.TOOL)


class ConnectionPage(QTabWidget):
    """Compose independent model and tool forms under Connections."""

    command = Signal(str, object)

    def __init__(self) -> None:
        """Create category tabs and forward commands to the desktop worker.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__()
        self.models = ModelConnectionPage()
        self.tools = ToolConnectionPage()
        self._command_page: ConnectionEditor = self.models
        self.addTab(self.models, "Models")
        self.addTab(self.tools, "Tools")
        self.models.command.connect(self._forward)
        self.tools.command.connect(self._forward)

    @property
    def notice(self) -> QLabel:
        """Route asynchronous feedback to the form that submitted the command.

        Parameters
        ----------
        None

        Returns
        -------
        QLabel
            Originating editor's status label.
        """
        return self._command_page.notice

    def _forward(self, action: str, payload: object) -> None:
        """Remember the submitting editor and forward its detached command.

        Parameters
        ----------
        action : str
            Worker command name.
        payload : object
            Secret-free settings plus a separately supplied replacement secret.

        Returns
        -------
        None
        """
        sender = self.sender()
        if isinstance(sender, ConnectionEditor):
            self._command_page = sender
        self.command.emit(action, payload)

    def refresh(self, records: tuple[Connection, ...]) -> None:
        """Refresh both category lists without replacing unfinished forms.

        Parameters
        ----------
        records : tuple of Connection
            Persisted settings in the existing storage schema.

        Returns
        -------
        None
        """
        self.models.refresh(records)
        self.tools.refresh(records)
