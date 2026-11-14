"""Desktop resource usage labels and small time-series charts."""

from collections import deque

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from amethyst.application.resource_monitor import ResourceSnapshot


class ResourceChart(QWidget):
    """Draw bounded percentage samples as a lightweight line chart."""

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        """Create a chart with an independent rolling sample window.

        Parameters
        ----------
        color : str
            CSS-compatible line color.
        parent : QWidget or None
            Optional owning widget.

        Returns
        -------
        None
        """
        super().__init__(parent)
        self.color = color
        self.samples: deque[float] = deque(maxlen=60)
        self.setMinimumHeight(100)

    def add_sample(self, value: float | None) -> None:
        """Add a measurable sample and repaint the chart.

        Parameters
        ----------
        value : float or None
            Percentage from zero to one hundred, or unavailable telemetry.

        Returns
        -------
        None
        """
        if value is not None:
            self.samples.append(max(0.0, min(100.0, value)))
        self.update()

    def paintEvent(self, event) -> None:
        """Render grid lines and the available rolling percentage series.

        Parameters
        ----------
        event : QPaintEvent
            Qt paint event for this widget.

        Returns
        -------
        None
        """
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.setPen(QPen(QColor("#3b3943"), 1))
        for fraction in (0.0, 0.5, 1.0):
            y = rect.bottom() - int(rect.height() * fraction)
            painter.drawLine(rect.left(), y, rect.right(), y)
        if len(self.samples) < 2:
            return
        painter.setPen(QPen(QColor(self.color), 2))
        points = [
            (
                rect.left() + int(index * rect.width() / (len(self.samples) - 1)),
                rect.bottom() - int(value * rect.height() / 100),
            )
            for index, value in enumerate(self.samples)
        ]
        for start, end in zip(points, points[1:]):
            painter.drawLine(*start, *end)


class ResourcePage(QWidget):
    """Show machine-wide CPU, RAM, and detectable NVIDIA GPU usage."""

    def __init__(self) -> None:
        """Build a compact resource panel with three rolling charts.

        Returns
        -------
        None
        """
        super().__init__()
        layout = QVBoxLayout(self)
        self.labels: dict[str, QLabel] = {}
        self.charts = {
            "CPU": ResourceChart("#a77de2"),
            "RAM": ResourceChart("#60c3ad"),
            "GPU": ResourceChart("#f0b35a"),
        }
        for name, chart in self.charts.items():
            label = QLabel(f"{name}: waiting for telemetry")
            label.setObjectName("eyebrow")
            self.labels[name] = label
            layout.addWidget(label)
            layout.addWidget(chart)
        self.ollama_label = QLabel("Ollama: not detected")
        self.ollama_label.setObjectName("eyebrow")
        layout.addWidget(self.ollama_label)
        self.note = QLabel(
            "GPU device selection and control are not performed by this monitor. "
            "Ollama VRAM is reported only when its local API provides it."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)

    def update_snapshot(self, snapshot: ResourceSnapshot) -> None:
        """Append one sample and update readable metric labels.

        Parameters
        ----------
        snapshot : ResourceSnapshot
            Best-effort telemetry sample from the worker.

        Returns
        -------
        None
        """
        values = {
            "CPU": snapshot.cpu_percent,
            "RAM": snapshot.memory_percent,
            "GPU": snapshot.gpu_percent,
        }
        for name, value in values.items():
            self.charts[name].add_sample(value)
            text = "unavailable" if value is None else f"{value:.1f}%"
            self.labels[name].setText(f"{name}: {text}")
        gpu_memory = snapshot.gpu_memory_percent
        if gpu_memory is not None:
            gpu_text = (
                "unavailable"
                if snapshot.gpu_percent is None
                else f"{snapshot.gpu_percent:.1f}%"
            )
            self.labels["GPU"].setText(
                f"GPU: {gpu_text} · memory {gpu_memory:.1f}%"
            )
        if snapshot.ollama_models:
            memory = (
                f" · VRAM {snapshot.ollama_vram_bytes / 1_000_000_000:.1f} GB"
                if snapshot.ollama_vram_bytes is not None
                else ""
            )
            self.ollama_label.setText(
                f"Ollama: {', '.join(snapshot.ollama_models)}{memory}"
            )
        else:
            self.ollama_label.setText(
                "Ollama: no active models or local API unavailable"
            )
