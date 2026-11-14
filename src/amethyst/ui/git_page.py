"""Read-only branch graph rendered from the active chat workspace metadata."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from amethyst.security.git_metadata import GitBranch


class GitGraph(QWidget):
    """Draw local branch tips as a small read-only branch flow."""

    def __init__(self) -> None:
        """Create an empty graph canvas.

        Returns
        -------
        None
        """
        super().__init__()
        self.branches: tuple[GitBranch, ...] = ()
        self.setMinimumHeight(120)

    def set_branches(self, branches: tuple[GitBranch, ...]) -> None:
        """Replace the visible branch catalog and repaint the graph.

        Parameters
        ----------
        branches : tuple of GitBranch
            Branch names, short tip IDs, and active branch flag.

        Returns
        -------
        None
        """
        self.branches = branches
        self.setMinimumHeight(max(120, 44 * len(branches) + 32))
        self.update()

    def paintEvent(self, event) -> None:
        """Draw one lane and labeled tip for each discovered branch.

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
        if not self.branches:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(12, 28, "No local branch metadata found.")
            return
        trunk_x = 28
        painter.setPen(QPen("#6f6879", 2))
        painter.drawLine(trunk_x, 20, trunk_x, 20 + 44 * (len(self.branches) - 1))
        for index, branch in enumerate(self.branches):
            y = 20 + 44 * index
            color = "#a77de2" if branch.current else "#76717d"
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(trunk_x, y, 58, y)
            painter.setBrush(QColor(color))
            painter.drawEllipse(trunk_x - 5, y - 5, 10, 10)
            painter.drawText(72, y + 5, f"{branch.name}  ·  {branch.commit}")


class GitPage(QWidget):
    """Display local branch metadata and offer an explicit refresh control."""

    refresh_requested = Signal()

    def __init__(self) -> None:
        """Build branch graph, safe-read disclosure, and refresh control.

        Returns
        -------
        None
        """
        super().__init__()
        layout = QVBoxLayout(self)
        self.notice = QLabel(
            "Branch names are read from workspace Git metadata. No Git commands "
            "or branch operations are run. Grant workspace reads in the chat first."
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.graph = GitGraph()
        layout.addWidget(self.graph)
        refresh = QPushButton("Refresh branches")
        refresh.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh)
        layout.addStretch(1)

    def set_branches(self, branches: tuple[GitBranch, ...]) -> None:
        """Render an updated read-only branch listing.

        Parameters
        ----------
        branches : tuple of GitBranch
            Branch metadata returned by the workspace reader.

        Returns
        -------
        None
        """
        self.graph.set_branches(branches)
        current = next((branch.name for branch in branches if branch.current), None)
        self.notice.setText(
            f"{len(branches)} local branches · current: {current or 'detached HEAD'}. "
            "Read-only metadata view."
        )
