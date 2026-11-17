"""Trusted permission and diagnostic controls separated from chat navigation."""

from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget


class PermissionsPage(QWidget):
    """Present grants and approvals without deciding effective authorization."""

    command = Signal(str, object)
    refresh_requested = Signal()

    def __init__(self) -> None:
        """Build explicit workspace, revocation, and log-retention controls.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        super().__init__()
        layout = QVBoxLayout(self)
        self.notice = QLabel("Workspace access is managed separately for each chat.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        for title, handler in (("Refresh permissions and logs", self.refresh_requested.emit),):
            button = QPushButton(title)
            button.clicked.connect(handler)
            layout.addWidget(button)
        layout.addWidget(QLabel("Read grants and action approvals"))
        self.permissions = QListWidget()
        self.permissions.setAccessibleName("Active permissions and approvals")
        layout.addWidget(self.permissions)
        revoke = QPushButton("Revoke selected permission / approval")
        revoke.clicked.connect(self._revoke)
        layout.addWidget(revoke)
        layout.addWidget(
            QLabel("Redacted diagnostic records (expire after seven days)")
        )
        self.logs = QListWidget()
        layout.addWidget(self.logs)
        for title, action in (
            ("Save selected log permanently", "save_log"),
            ("Delete selected log", "delete_log"),
        ):
            button = QPushButton(title)
            button.clicked.connect(partial(self._log, action))
            layout.addWidget(button)

    def refresh(self, snapshot: dict) -> None:
        """Render detached permissions and operational state from the worker.

        Parameters
        ----------
        snapshot : dict
            Current grants, approvals, logs, and workspace/credential status.

        Returns
        -------
        None
        """
        self.permissions.clear()
        for grant in snapshot["grants"]:
            self.permissions.addItem(f"Read: {grant.tool_name} - {grant.resource}")
            self.permissions.item(self.permissions.count() - 1).setData(
                Qt.ItemDataRole.UserRole, ("revoke_grant", grant.id)
            )
        for approval in snapshot["approvals"]:
            self.permissions.addItem(
                f"Approval {approval.request.id}: {approval.status.value}"
            )
            self.permissions.item(self.permissions.count() - 1).setData(
                Qt.ItemDataRole.UserRole, ("revoke_approval", approval.request.id)
            )
        self.logs.clear()
        self.logs.addItems(list(snapshot["logs"]))
        storage = (
            "memory only; re-enter after restart"
            if snapshot["memory_only"]
            else "OS credential store"
        )
        self.notice.setText(
            f"Credentials: {storage}. "
            f"Sandbox: {'enabled' if snapshot['sandbox_enabled'] else 'disabled'}. "
            "Workspace grants are saved with their chat and can be revoked there."
        )

    def _revoke(self) -> None:
        """Request revocation of the selected grant or action approval.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        item = self.permissions.currentItem()
        if item:
            action, identifier = item.data(Qt.ItemDataRole.UserRole)
            self.command.emit(action, identifier)

    def _log(self, action: str) -> None:
        """Request the selected diagnostic record's explicit retention action.

        Parameters
        ----------
        action : str
            Save-permanently or delete command.

        Returns
        -------
        None
        """
        item = self.logs.currentItem()
        if item:
            self.command.emit(action, item.text())
