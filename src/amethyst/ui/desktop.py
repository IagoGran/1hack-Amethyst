"""Integrated desktop using the real agent, durable history, and safe controls."""

import time
from uuid import uuid4

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from amethyst.configuration.catalog import MODEL_KINDS
from amethyst.domain.contracts import (
    ApprovalRequest,
    ActionRecord,
    StartTask,
    TaskEvent,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
    ToolResult,
    Usage,
)
from amethyst.domain.tasks import TASK_STATUS_LABELS, TaskStatus
from amethyst.domain.tasks import TERMINAL_STATUSES as TERMINAL
from amethyst.ui.branding import APP_ICON_PATH
from amethyst.ui.connection_page import ConnectionPage
from amethyst.ui.conversation_page import ConversationPage
from amethyst.ui.desktop_worker import DesktopWorker
from amethyst.ui.git_page import GitPage
from amethyst.ui.limits_page import LimitsPage
from amethyst.ui.permissions_page import PermissionsPage
from amethyst.ui.resource_page import ResourcePage
from amethyst.ui.sidebar import NavigationSidebar
from amethyst.ui.skill_page import SkillPage
from amethyst.ui.theme import APP_STYLE


class DesktopWindow(QMainWindow):
    """Present real service state and send trusted user decisions to its thread."""

    def __init__(self, worker: DesktopWorker) -> None:
        """Compose navigation and start asynchronous local-session initialization.

        Parameters
        ----------
        worker : DesktopWorker
            Persistent application event-loop owner.

        Returns
        -------
        None
        """
        super().__init__()
        self.worker = worker
        self.conversation_id: str | None = None
        self.busy = False
        self.closing = False
        self.closed = False
        self.history_busy = False
        self.approval_dialog: QDialog | None = None
        self._approval_active = False
        self.snapshot: dict = {}
        self._limits_loaded = False
        self._task_started_at: float | None = None
        self._last_model_id: str | None = None
        self._resource_request_pending = False
        self.setWindowTitle("Amethyst")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(APP_STYLE)
        self._build()
        self._duration_timer = QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._update_task_duration)
        self._resource_timer = QTimer(self)
        self._resource_timer.setInterval(1000)
        self._resource_timer.timeout.connect(self._request_resources)
        self.content.setEnabled(False)
        worker.ready.connect(self._ready)
        worker.result.connect(self._result)
        worker.failed.connect(self._failure)
        worker.event_received.connect(self._event)
        worker.finished.connect(self._stopped)
        worker.start()

    def _build(self) -> None:
        """Reuse the desktop visual shell around integrated application pages.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        root = QWidget()
        self.content = root
        layout = QHBoxLayout(root)
        self.sidebar = NavigationSidebar()
        self.pages = QStackedWidget()
        self.chat = ConversationPage(
            disclosure=(
                "Local conversation storage. Responses use your selected model. "
                "Configure a model in Connections to begin."
            )
        )
        self.connections = ConnectionPage()
        self.limits = LimitsPage()
        self.settings = QTabWidget()
        self.settings.addTab(self.connections, "Connections")
        self.settings.addTab(self.limits, "Operational limits")
        self.skills = SkillPage()
        self.permission_page = PermissionsPage()
        self.resources = ResourcePage()
        self.git_page = GitPage()
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Task status, tool results, and sources")
        self.page_indexes = {}
        for name, page in (
            ("Chat", self._chat_area()),
            ("Connections", self.settings),
            ("Skills", self.skills),
            ("Permissions", self.permission_page),
            ("Resources", self.resources),
            ("Git branches", self.git_page),
            ("Task details", self.details),
        ):
            self.page_indexes[name] = self.pages.addWidget(page)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self.sidebar.page_requested.connect(self._navigate)
        self.sidebar.new_conversation_requested.connect(self._new)
        self.sidebar.recent_conversation_requested.connect(self._open)
        self.sidebar.delete_conversation_requested.connect(self._delete)
        self.chat.message_submitted.connect(self._send)
        self.chat.workspace_requested.connect(self._workspace)
        self.chat.workspace_access_requested.connect(self._workspace_access)
        self.chat.undo_requested.connect(self._undo_last)
        self.connections.command.connect(self.worker.submit)
        self.limits.command.connect(self.worker.submit)
        self.skills.command.connect(self.worker.submit)
        self.permission_page.command.connect(self.worker.submit)
        self.permission_page.refresh_requested.connect(self._refresh)
        self.git_page.refresh_requested.connect(
            lambda: self.worker.submit("git_branches")
        )

    def _chat_area(self) -> QWidget:
        """Add model selection, cancellation, and explicit budget controls.

        Parameters
        ----------
        None

        Returns
        -------
        QWidget
            Integrated chat page.
        """
        area = QWidget()
        layout = QVBoxLayout(area)
        row = QHBoxLayout()
        row.addWidget(QLabel("Model"))
        self.models = QComboBox()
        self.models.setAccessibleName("Model connection")
        row.addWidget(self.models, 1)
        self.tokens = QSpinBox()
        self.tokens.setRange(1, 1_000_000)
        self.tokens.setValue(10_000)
        self.tokens.setSuffix(" tokens")
        self.tokens.setAccessibleName("Additional task token budget")
        row.addWidget(self.tokens)
        self.increase = QPushButton("Increase budget")
        self.increase.setEnabled(False)
        self.increase.clicked.connect(self._budget)
        row.addWidget(self.increase)
        self.cancel = QPushButton("Cancel task")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self._cancel)
        row.addWidget(self.cancel)
        layout.addLayout(row)
        layout.addWidget(self.chat)
        return area

    def _ready(self) -> None:
        """Enable the UI after repositories and credentials are initialized.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.content.setEnabled(True)
        if self.closing:
            self.worker.submit("close")
        else:
            self._refresh()

    def _refresh(self) -> None:
        """Request a detached snapshot of persistent and session state.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.worker.submit("snapshot")

    def _navigate(self, name: str) -> None:
        """Select a navigation page.

        Parameters
        ----------
        name : str
            Page name from the sidebar.

        Returns
        -------
        None
        """
        self.pages.setCurrentIndex(self.page_indexes.get(name, 0))
        self.sidebar.set_active_page(name)
        if name == "Resources":
            self._request_resources()
            self._resource_timer.start()
        else:
            self._resource_timer.stop()
        if name == "Git branches":
            self.worker.submit("git_branches")

    def _new(self) -> None:
        """Prepare a fresh conversation while preserving saved history.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self.busy or self.history_busy:
            return
        self.conversation_id = uuid4().hex
        self.sidebar.set_active_conversation(None)
        self.chat.reset()
        self.worker.submit("activate_conversation", self.conversation_id)
        self._navigate("Chat")

    def _open(self, identifier: str) -> None:
        """Load a saved conversation for viewing and resumption.

        Parameters
        ----------
        identifier : str
            Persistent conversation ID.

        Returns
        -------
        None
        """
        if not self.busy and not self.history_busy:
            self.history_busy = True
            self.worker.submit("open", identifier)

    def _delete(self, identifier: str) -> None:
        """Confirm and delete a saved conversation when no task is active.

        Parameters
        ----------
        identifier : str
            Persistent conversation ID.

        Returns
        -------
        None
        """
        if self.busy or self.history_busy:
            return
        if (
            QMessageBox.question(
                self, "Delete conversation?", "Permanently delete this conversation?"
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        if identifier == self.conversation_id:
            self._new()
        self.history_busy = True
        self.worker.submit("delete_conversation", identifier)

    def _send(self, prompt: str) -> None:
        """Submit a prompt through the real service without pre-saving messages.

        Parameters
        ----------
        prompt : str
            User request.

        Returns
        -------
        None
        """
        if self.busy or self.history_busy:
            return
        model = self.models.currentData()
        if not model:
            self.statusBar().showMessage("Add and enable a model in Connections.")
            return
        self.conversation_id = self.conversation_id or uuid4().hex
        if model != self._last_model_id:
            if self._last_model_id:
                self.details.appendPlainText(f"Model changed to {model}.")
            self._last_model_id = model
        self._task_started_at = time.monotonic()
        self._duration_timer.start()
        self.busy = True
        self.models.setEnabled(False)
        self.connections.setEnabled(False)
        self.limits.setEnabled(False)
        self.skills.setEnabled(False)
        self.chat.begin_turn(prompt)
        self.details.clear()
        self.worker.submit(
            "send",
            StartTask(self.conversation_id, prompt, model, self.skills.selected_ids()),
        )

    def _event(
        self, event: TaskEvent | ApprovalRequest | ActionRecord | tuple
    ) -> None:
        """Render sequenced output, terminal states, approvals, and tool sources.

        Parameters
        ----------
        event : TaskEvent, ApprovalRequest, ActionRecord, or tuple
            Application event or direct worker notification.

        Returns
        -------
        None
        """
        if isinstance(event, ApprovalRequest):
            self._approval(event)
            return
        if isinstance(event, ActionRecord):
            files = ", ".join(event.file_paths) or "no file paths"
            self.details.appendPlainText(
                f"{event.tool} · {event.status}: {event.summary} [{files}]"
            )
            if event.tool == "model.selection":
                self.chat.add_notice(event.summary)
            return
        if isinstance(event, tuple) and event[0] == "ollama_progress":
            self.connections.models.notice.setText(f"Ollama pull: {event[1]}")
            return
        payload = event.payload
        if isinstance(payload, TextDelta):
            self.chat.append_delta(payload.text)
        elif isinstance(payload, Usage):
            message = (
                f"Token budget: {payload.task_total_tokens:,} charged, "
                f"{payload.task_remaining_tokens:,} remaining."
            )
            self.statusBar().showMessage(message)
            self.details.appendPlainText(message)
        elif isinstance(payload, TaskStateChanged):
            label = TASK_STATUS_LABELS[payload.status]
            self.statusBar().showMessage(label + ": " + payload.message)
            self.details.appendPlainText(label + ": " + payload.message)
            self.chat.set_activity(
                label + (f" · {payload.message}" if payload.message else "")
            )
            self.cancel.setEnabled(payload.status not in TERMINAL)
            self.increase.setEnabled(payload.status == TaskStatus.PAUSED_FOR_BUDGET)
            if payload.status in TERMINAL:
                self.chat.finish_turn(label)
                if self.approval_dialog:
                    self._approval_active = False
                    self.approval_dialog.reject()
        elif isinstance(payload, TaskFailure):
            self.details.appendPlainText(payload.message)
            self.chat.show_error(payload.message, payload.stacktrace)
            # A failure event can arrive before the terminal-state event. Release
            # the composer here as well so an interrupted event stream cannot
            # leave the conversation unusable.
            self._idle()
            self.chat.finish_turn("Failed")
            self._refresh()
        elif isinstance(payload, ToolResult):
            text = ("[Truncated] " if payload.truncated else "") + payload.content
            self.details.appendPlainText(text)
            for source in payload.sources:
                self.details.appendPlainText(source.url or source.identifier)
        elif isinstance(payload, ActionRecord):
            files = ", ".join(payload.file_paths) or "no file paths"
            self.details.appendPlainText(
                f"{payload.tool} · {payload.status}: {payload.summary} [{files}]"
            )
        elif isinstance(payload, ApprovalRequest):
            self._approval(payload)

    def _approval(self, proposal: ApprovalRequest) -> None:
        """Display every exact action, scope, and diff before accepting a decision.

        Parameters
        ----------
        proposal : ApprovalRequest
            Bound action or explicitly enumerated batch.

        Returns
        -------
        None
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Review proposed actions")
        dialog.resize(760, 580)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setAccessibleName("Exact actions, resource scopes, and reviewed diffs")
        for action in proposal.actions:
            text.appendPlainText(
                f"{action.tool_name}: {action.summary}\n"
                f"Scope: {', '.join(action.resource_scope)}\n"
                f"High impact: {action.high_impact}\n"
            )
            for change in action.changes:
                text.appendPlainText(change.path + "\n" + change.diff)
        layout.addWidget(text)
        buttons = QDialogButtonBox()
        buttons.addButton(
            "Approve listed actions", QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton("Deny", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        self.approval_dialog = dialog
        self._approval_active = True
        dialog.finished.connect(
            lambda code: (
                self.worker.submit(
                    "decide", (proposal.id, code == QDialog.DialogCode.Accepted)
                )
                if self._approval_active
                else None
            )
        )
        dialog.finished.connect(self._approval_closed)
        dialog.open()
        self._refresh()

    def _approval_closed(self, code: int) -> None:
        """Release the completed approval dialog reference.

        Parameters
        ----------
        code : int
            Qt dialog result.

        Returns
        -------
        None
        """
        if self.approval_dialog:
            self.approval_dialog.deleteLater()
        self.approval_dialog = None
        self._approval_active = False

    def _result(self, action: str, value) -> None:
        """Apply detached repository and control results on Qt's thread.

        Parameters
        ----------
        action : str
            Completed command.
        value : object
            Safe command result.

        Returns
        -------
        None
        """
        if action == "snapshot":
            self._show_snapshot(value)
        elif action == "open":
            self.history_busy = False
            self.conversation_id = value.id
            self.chat.load_conversation(value)
            self._show_action_history(value)
            self.sidebar.set_active_conversation(value.id)
            self._navigate("Chat")
        elif action == "send":
            self._idle()
            self.sidebar.set_active_conversation(value.id)
            self.chat.set_workspace(
                value.workspace_root,
                value.workspace_read_granted,
                len(value.undo_records),
            )
            self._refresh()
        elif action in {"workspace", "workspace_access"}:
            self.history_busy = False
            if value.id == self.conversation_id:
                self.chat.set_workspace(
                    value.workspace_root,
                    value.workspace_read_granted,
                    len(value.undo_records),
                )
            self._refresh()
        elif action == "undo_last":
            self.history_busy = False
            self.conversation_id = value.id
            self.chat.load_conversation(value)
            self._show_action_history(value)
            self.details.appendPlainText("The latest file change was reverted.")
            self._refresh()
        elif action == "warnings":
            for warning in value:
                self.details.appendPlainText(warning)
        elif action == "test_connection":
            if value.available:
                self.connections.notice.setText(value.message)
            else:
                self.connections.report_error(value.message)
        elif action == "resources":
            self._resource_request_pending = False
            self.resources.update_snapshot(value)
        elif action in {"ollama_list", "ollama_pull"}:
            names = ", ".join(value) if value else "No local models found."
            self.connections.models.notice.setText(f"Local Ollama models: {names}")
        elif action == "git_branches":
            self.git_page.set_branches(value)
        elif action not in {"close", "cancel", "budget"}:
            self.history_busy = False
            self.statusBar().showMessage("Operation completed.")
            self._refresh()

    def _show_snapshot(self, value: dict) -> None:
        """Update history, settings, permission scopes, and credential disclosure.

        Parameters
        ----------
        value : dict
            Detached session snapshot.

        Returns
        -------
        None
        """
        self.snapshot = value
        if not self._limits_loaded:
            self.limits.refresh(value["limits"])
            self._limits_loaded = True
        self.sidebar.set_conversations(value["conversations"])
        selected = self.models.currentData()
        self.models.clear()
        for connection in value["connections"]:
            if connection.enabled and connection.kind in MODEL_KINDS:
                self.models.addItem(connection.id, connection.id)
        index = self.models.findData(selected)
        if index >= 0:
            self.models.setCurrentIndex(index)
        self.connections.refresh(value["connections"])
        self.skills.refresh(value["skills"])
        self.permission_page.refresh(value)
        active = next(
            (
                item
                for item in value["conversations"]
                if item.id == self.conversation_id
            ),
            None,
        )
        if active:
            self.chat.set_workspace(
                active.workspace_root,
                active.workspace_read_granted,
                len(active.undo_records),
            )

    def _show_action_history(self, conversation) -> None:
        """Render retained minimal action summaries for a reopened conversation.

        Parameters
        ----------
        conversation : Conversation
            Persisted conversation with safe action metadata.

        Returns
        -------
        None
        """
        self.details.clear()
        for action in conversation.action_history:
            files = ", ".join(action.file_paths) or "no file paths"
            self.details.appendPlainText(
                f"{action.created_at} · {action.tool} · {action.status}: "
                f"{action.summary} [{files}]"
            )

    def _idle(self) -> None:
        """Restore configuration and composer controls after task finalization.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.busy = False
        self.models.setEnabled(True)
        self.connections.setEnabled(True)
        self.limits.setEnabled(True)
        self.skills.setEnabled(True)
        self.cancel.setEnabled(False)
        self.increase.setEnabled(False)
        self._duration_timer.stop()
        self._task_started_at = None

    def _failure(
        self, action: str, message: str, stacktrace: tuple[str, ...] = ()
    ) -> None:
        """Show a safe failure and release controls for failed task submission.

        Parameters
        ----------
        action : str
            Failed command.
        message : str
            Filtered error description.
        stacktrace : tuple of str
            Safe frame locations for local diagnostics.

        Returns
        -------
        None
        """
        self.statusBar().showMessage(message)
        self.details.appendPlainText(message)
        self.history_busy = False
        if action == "send":
            self._idle()
            self.chat.show_error(message, stacktrace)
            self._refresh()
        if action in {"save_connection", "test_connection"}:
            self.connections.report_error(message)
        elif action in {"ollama_list", "ollama_pull"}:
            self.connections.models.notice.setText(message)
        elif action == "git_branches":
            self.git_page.notice.setText(message)
        elif action == "resources":
            self._resource_request_pending = False
            self.resources.note.setText(message)

    def _cancel(self) -> None:
        """Request cancellation while leaving final state to application events.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.cancel.setEnabled(False)
        self.statusBar().showMessage("Cancelling...")
        self.worker.submit("cancel")

    def _budget(self) -> None:
        """Send an explicit user-selected token-budget increase.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.increase.setEnabled(False)
        self.worker.submit("budget", self.tokens.value())

    def _update_task_duration(self) -> None:
        """Display elapsed task time while generation or tools are active.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self._task_started_at is None:
            return
        elapsed = int(time.monotonic() - self._task_started_at)
        self.statusBar().showMessage(
            f"Task running · {elapsed // 60:02}:{elapsed % 60:02}"
        )

    def _request_resources(self) -> None:
        """Request one telemetry sample without overlapping worker reads.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if not self._resource_request_pending:
            self._resource_request_pending = True
            self.worker.submit("resources")

    def _workspace(self) -> None:
        """Select a directory boundary for the active conversation.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self.busy or self.history_busy:
            return
        if self.conversation_id is None:
            self.conversation_id = uuid4().hex
            self.worker.submit("activate_conversation", self.conversation_id)
        path = QFileDialog.getExistingDirectory(self, "Select workspace")
        if path and self.conversation_id:
            self.history_busy = True
            self.worker.submit("workspace", (self.conversation_id, path))

    def _workspace_access(self, granted: bool) -> None:
        """Persist and apply the active conversation's workspace read grant.

        Parameters
        ----------
        granted : bool
            Whether read access should be active for this conversation.

        Returns
        -------
        None
        """
        if self.busy or self.history_busy or not self.conversation_id:
            return
        self.history_busy = True
        self.worker.submit(
            "workspace_access", (self.conversation_id, granted)
        )

    def _undo_last(self) -> None:
        """Request the latest inverse file diff for explicit approval.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self.busy or self.history_busy or not self.conversation_id:
            return
        self.history_busy = True
        self.worker.submit("undo_last", self.conversation_id)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Wait asynchronously for task cleanup before destroying the Qt thread.

        Parameters
        ----------
        event : QCloseEvent
            Window-close request.

        Returns
        -------
        None
        """
        if self.closed:
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.content.setEnabled(False)
            self.statusBar().showMessage(
                "Closing tasks and expiring session permissions..."
            )
            self.worker.submit("close")

    def _stopped(self) -> None:
        """Close the window only after its application worker has terminated.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.closed = True
        if self.closing:
            self.close()
