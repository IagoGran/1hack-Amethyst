"""A2 chat screen with task controls, scenario selection, and transcript."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import (
    TaskEvent,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.ui.base_page import BasePage


class A2ChatPage(BasePage):
    """Present the chat workflow and explicit controls for a fake task."""

    message_submitted = Signal(str, str)
    cancel_requested = Signal()
    budget_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the transcript, scenario controls, and message composer."""
        super().__init__("Chat", parent)
        self._build_content()

    def _build_content(self) -> None:
        """Arrange preview disclosure, task controls, transcript, and composer."""
        self._add_disclosure()
        self._build_task_controls()
        self._build_transcript()
        self._build_composer()
        self._progress_updates = 0

    def _add_disclosure(self) -> None:
        """Disclose the fake service and its lack of model or workspace access."""
        banner = QLabel(
            "A2 INTERACTION PREVIEW · FAKE SERVICE · No model, tools, "
            "file access, or persistence"
        )
        banner.setObjectName("demoBanner")
        banner.setWordWrap(True)
        self.content_layout.addWidget(banner)

    def _build_task_controls(self) -> None:
        """Create scenario selection and cancellation/budget actions."""
        row = QHBoxLayout()
        row.addWidget(QLabel("Scenario"))
        self._scenario = QComboBox()
        self._scenario.addItem("Code generation", "preview:normal")
        self._scenario.addItem("Budget pause", "preview:budget")
        self._scenario.addItem("Simulated error", "preview:failure")
        row.addWidget(self._scenario)
        row.addStretch(1)
        self._budget = QSpinBox()
        self._budget.setRange(1, 100_000)
        self._budget.setValue(1_000)
        self._budget.setSuffix(" tokens")
        row.addWidget(self._budget)
        self._increase = QPushButton("Increase budget")
        self._increase.setEnabled(False)
        self._increase.clicked.connect(self._request_budget)
        row.addWidget(self._increase)
        self._cancel = QPushButton("Cancel task")
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self.cancel_requested.emit)
        row.addWidget(self._cancel)
        self.content_layout.addLayout(row)

    def _build_transcript(self) -> None:
        """Create an accessible read-only transcript with scrolling."""
        self._transcript = QPlainTextEdit()
        self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(True)
        self._transcript.setAccessibleName("Conversation messages")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._transcript)
        self.content_layout.addWidget(scroll, 1)

    def _build_composer(self) -> None:
        """Create prompt entry, task status, and send action."""
        row = QHBoxLayout()
        self._prompt = QLineEdit()
        self._prompt.setObjectName("prompt")
        self._prompt.setPlaceholderText(
            "Describe code to generate or an error to debug…"
        )
        self._prompt.setAccessibleName("Task request")
        self._prompt.returnPressed.connect(self._submit)
        row.addWidget(self._prompt, 1)
        self._status = QLabel("Ready")
        self._status.setObjectName("statusPill")
        self._status.setAccessibleName("Task status")
        row.addWidget(self._status)
        self._send = QPushButton("Send ↑")
        self._send.setObjectName("send")
        self._send.clicked.connect(self._submit)
        row.addWidget(self._send)
        self.content_layout.addLayout(row)

    def _submit(self) -> None:
        """Submit non-empty prompts with the selected fake scenario."""
        prompt = self._prompt.text().strip()
        if prompt and self._send.isEnabled():
            self.message_submitted.emit(prompt, self._scenario.currentData())

    def _request_budget(self) -> None:
        """Emit the user-selected token increase and prevent duplicate clicks."""
        self._increase.setEnabled(False)
        self._status.setText("Requesting budget…")
        self.budget_requested.emit(self._budget.value())

    def begin_task(self, prompt: str) -> None:
        """Append the user prompt and disable task creation while running."""
        self._transcript.appendPlainText(f"YOU\n{prompt}\n\nAMETHYST · FAKE PREVIEW\n")
        self._prompt.clear()
        self._progress_updates = 0
        self._set_busy(True)
        self._status.setText("Starting…")
        self._scenario.setEnabled(False)

    def render_event(self, event: TaskEvent) -> None:
        """Render one typed event and enable controls for the reported state."""
        payload = event.payload
        if isinstance(payload, TaskStateChanged):
            self._show_state(payload.status, payload.message)
        elif isinstance(payload, TextDelta):
            self._transcript.insertPlainText(payload.text)
            self._transcript.ensureCursorVisible()
            self._progress_updates += 1
            self._status.setText(
                f"Running · {self._progress_updates} updates received"
            )
        elif isinstance(payload, TaskFailure):
            self._transcript.appendPlainText(f"\nTask failed: {payload.message}")

    def _show_state(self, status: TaskStatus, message: str) -> None:
        """Update status text and expose actions valid for the current state."""
        labels = {
            TaskStatus.PENDING: "Pending",
            TaskStatus.RUNNING: "Running",
            TaskStatus.AWAITING_APPROVAL: "Awaiting approval",
            TaskStatus.PAUSED_FOR_BUDGET: "Paused for budget",
            TaskStatus.COMPLETED: "Completed",
            TaskStatus.CANCELLED: "Cancelled",
            TaskStatus.FAILED: "Failed",
        }
        self._status.setText(labels[status] + (f" · {message}" if message else ""))
        active = status in {TaskStatus.RUNNING, TaskStatus.PAUSED_FOR_BUDGET}
        self._cancel.setEnabled(active)
        self._increase.setEnabled(status == TaskStatus.PAUSED_FOR_BUDGET)
        if status in {TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.FAILED}:
            self._set_busy(False)
            self._scenario.setEnabled(True)

    def _set_busy(self, busy: bool) -> None:
        """Toggle composer actions and task controls for the active run."""
        self._send.setEnabled(not busy)
        self._prompt.setEnabled(not busy)
        self._cancel.setEnabled(busy)

    def show_error(self, message: str) -> None:
        """Show a safe service error and make the composer available again."""
        self._transcript.appendPlainText(f"\nUnable to complete task: {message}")
        self._status.setText("Failed")
        self._set_busy(False)
        self._scenario.setEnabled(True)
        self._increase.setEnabled(False)

    def show_control_acknowledgement(self, status: str) -> None:
        """Reflect the service's confirmed cancellation or budget state."""
        if status == TaskStatus.CANCELLED:
            self._status.setText("Cancelled · acknowledged")
        elif status == TaskStatus.RUNNING:
            self._status.setText("Running · budget increased")

    def set_cancelling(self) -> None:
        """Show that cancellation is pending until the service confirms it."""
        self._status.setText("Cancelling…")
        self._cancel.setEnabled(False)
