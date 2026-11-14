"""Reusable skill editing and explicit selection for the next chat turn."""

from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import Skill


class SkillPage(QWidget):
    """Manage durable skills and select which instructions to apply."""

    command = Signal(str, object)

    def __init__(self) -> None:
        """Build the skill editor and selection list.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Skills: select entries to apply to the next message."))
        self.items = QListWidget()
        self.items.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.items.currentRowChanged.connect(self.load)
        layout.addWidget(self.items)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Skill name")
        self.name.setAccessibleName("Skill name")
        self.condition = QLineEdit()
        self.condition.setPlaceholderText(
            "Optional automatic condition: contains:literal text"
        )
        self.instructions = QPlainTextEdit()
        self.instructions.setAccessibleName("Skill instructions")
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(True)
        for widget in (self.name, self.condition, self.instructions, self.enabled):
            layout.addWidget(widget)
        row = QHBoxLayout()
        for title, handler in (
            ("New", self.clear),
            ("Save", self.save),
            ("Delete", self.delete),
        ):
            button = QPushButton(title)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        self.records: tuple[Skill, ...] = ()
        self.identifier: str | None = None

    def refresh(self, records: tuple[Skill, ...]) -> None:
        """Refresh saved entries, preserving explicit selection by ID.

        Parameters
        ----------
        records : tuple of Skill
            Persisted skill snapshots.

        Returns
        -------
        None
        """
        selected = self.selected_ids()
        self.records = records
        self.items.blockSignals(True)
        self.items.clear()
        for record in records:
            self.items.addItem(record.name + ("" if record.enabled else " (disabled)"))
            self.items.item(self.items.count() - 1).setSelected(record.id in selected)
        self.items.blockSignals(False)

    def selected_ids(self) -> tuple[str, ...]:
        """Return enabled skills explicitly selected for the next task.

        Parameters
        ----------
        None

        Returns
        -------
        tuple of str
            Selected persistent identifiers.
        """
        return tuple(
            record.id
            for index, record in enumerate(self.records)
            if record.enabled and self.items.item(index).isSelected()
        )

    def load(self, index: int) -> None:
        """Load one skill into the editor.

        Parameters
        ----------
        index : int
            Selected list row.

        Returns
        -------
        None
        """
        if not 0 <= index < len(self.records):
            return
        record = self.records[index]
        self.identifier = record.id
        self.name.setText(record.name)
        self.instructions.setPlainText(record.instructions)
        self.condition.setText(record.condition or "")
        self.enabled.setChecked(record.enabled)

    def clear(self) -> None:
        """Prepare a new skill without deleting saved instructions.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.identifier = None
        self.name.clear()
        self.condition.clear()
        self.instructions.clear()
        self.enabled.setChecked(True)

    def save(self) -> None:
        """Persist the current skill through the worker.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self.name.text().strip() and self.instructions.toPlainText().strip():
            self.command.emit(
                "save_skill",
                Skill(
                    self.identifier or uuid4().hex,
                    self.name.text().strip(),
                    self.instructions.toPlainText(),
                    self.enabled.isChecked(),
                    self.condition.text().strip() or None,
                ),
            )

    def delete(self) -> None:
        """Delete the edited skill when it has a persistent identifier.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self.identifier:
            self.command.emit("delete_skill", self.identifier)
