"""User controls for approved configurable operational limits."""

from dataclasses import fields
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from amethyst.configuration.limits import Limits

LABELS = (
    "Tool timeout (seconds)",
    "Model inactivity timeout (seconds)",
    "Model total timeout (seconds)",
    "Command timeout (seconds)",
    "Task timeout (seconds)",
    "Task token budget",
    "Model input tokens",
    "Model output tokens",
    "Retrieval chunks",
    "Tokens per chunk",
    "SQL rows",
    "Tool output bytes",
    "Automatic retries",
)


class LimitsPage(QWidget):
    """Edit persistent limits applied to subsequent tasks."""

    command = Signal(str, object)

    def __init__(self) -> None:
        """Build labeled numeric fields from the shared limit contract.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.inputs: dict[str, QDoubleSpinBox] = {}
        for field, label in zip(fields(Limits), LABELS, strict=True):
            widget = QDoubleSpinBox()
            widget.setDecimals(2 if field.type is float else 0)
            widget.setRange(
                0 if field.name == "retries" else 1,
                2 if field.name == "retries" else 1_000_000_000,
            )
            widget.setAccessibleName(label)
            form.addRow(label, widget)
            self.inputs[field.name] = widget
        layout.addLayout(form)
        button = QPushButton("Save limits for subsequent tasks")
        button.clicked.connect(self.save)
        layout.addWidget(button)
        layout.addStretch()
        self.refresh(Limits())

    def refresh(self, limits: Limits) -> None:
        """Load current limits into the settings form.

        Parameters
        ----------
        limits : Limits
            Active application configuration.

        Returns
        -------
        None
        """
        for name, widget in self.inputs.items():
            widget.setValue(getattr(limits, name))

    def save(self) -> None:
        """Submit typed numeric settings for validation and persistence.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        values: dict[str, Any] = {
            field.name: (float if field.type is float else int)(
                self.inputs[field.name].value()
            )
            for field in fields(Limits)
        }
        self.command.emit("save_limits", Limits(**values))
