"""Check trusted permission controls after extracting the dedicated page."""

from PySide6.QtWidgets import QApplication, QPushButton

from amethyst.domain.contracts import Approval, ApprovalRequest, ProposedAction
from amethyst.security.permissions import PermissionService
from amethyst.ui.permissions_page import PermissionsPage


def test_permission_controls_preserve_exact_commands(qt_app: QApplication) -> None:
    """Keep grant, revocation, and diagnostic actions bound to selected IDs.

    Parameters
    ----------
    qt_app : QApplication
        Shared headless Qt event-loop owner.

    Returns
    -------
    None
    """
    page = PermissionsPage()
    commands: list[tuple[str, object]] = []
    page.command.connect(lambda action, value: commands.append((action, value)))
    grant = PermissionService("session").grant("tool", "resource")
    proposal = ApprovalRequest(
        "review",
        "task",
        "session",
        (ProposedAction("action", "tool", "Read resource", ("resource",), "digest"),),
    )
    page.refresh(
        {
            "grants": (grant,),
            "approvals": (Approval(proposal),),
            "logs": ("log-id",),
            "memory_only": True,
            "workspace": None,
            "sandbox_enabled": False,
        }
    )
    buttons = {button.text(): button for button in page.findChildren(QPushButton)}
    try:
        buttons["Allow reads in selected workspace for this session"].click()
        page.permissions.setCurrentRow(0)
        buttons["Revoke selected permission / approval"].click()
        page.permissions.setCurrentRow(1)
        buttons["Revoke selected permission / approval"].click()
        page.logs.setCurrentRow(0)
        buttons["Save selected log permanently"].click()
        buttons["Delete selected log"].click()
        assert commands == [
            ("grant_workspace", None),
            ("revoke_grant", grant.id),
            ("revoke_approval", "review"),
            ("save_log", "log-id"),
            ("delete_log", "log-id"),
        ]
        assert "memory only" in page.notice.text()
    finally:
        page.close()
        page.deleteLater()
        qt_app.processEvents()
