"""Chat screen with a fake S0 task stream for the A1 preview."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from amethyst.domain.contracts import (
    ApprovalRequest,
    TaskEvent,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
    ToolResult,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.ui.base_page import BasePage
from amethyst.ui.suggestion_card import SuggestionCard


class ChatPage(BasePage):
    """Present the composer and render ordered task events from S0."""

    message_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Construct the chat screen and connect prompt interactions."""
        super().__init__("Chat", parent)
        self._assistant_text = ""
        self._build_content()

    def _build_content(self) -> None:
        """Arrange demo banner, welcome view, transcript, and composer."""
        self._add_demo_banner()
        self._build_welcome()
        self._build_transcript()
        self._build_composer()

    def _add_demo_banner(self) -> None:
        """Disclose that this screen uses the S0 fake service."""
        banner = QLabel(
            "DEVELOPMENT PREVIEW · S0 FAKE SERVICE · No models, tools, "
            "file access, or persistence"
        )
        banner.setObjectName("demoBanner")
        banner.setWordWrap(True)
        self.content_layout.addWidget(banner)

    def _build_welcome(self) -> None:
        """Create the empty state and connect its suggested prompts."""
        self._welcome = QWidget()
        layout = QVBoxLayout(self._welcome)
        layout.setContentsMargins(0, 26, 0, 12)
        layout.addStretch(1)
        self._add_welcome_heading(layout)
        self._add_workspace_badge(layout)
        self._add_suggestions(layout)
        layout.addStretch(1)
        self.content_layout.addWidget(self._welcome, 1)

    def _add_welcome_heading(self, layout: QVBoxLayout) -> None:
        """Add the title and short explanation for an empty conversation."""
        logo = QLabel("✦")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("color: #b895ff; font-size: 34pt;")
        heading = QLabel("What are we building today?")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet("font-size: 22pt; font-weight: 650;")
        intro = QLabel("Ask about your codebase, request a change, or explore an idea.")
        intro.setObjectName("muted")
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)
        layout.addWidget(heading)
        layout.addWidget(intro)

    def _add_workspace_badge(self, layout: QVBoxLayout) -> None:
        """Show the workspace name as local preview context."""
        badge = QLabel("●  1hack-Amethyst   ·   Current workspace")
        badge.setObjectName("statusPill")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMaximumWidth(330)
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignCenter)

    def _add_suggestions(self, layout: QVBoxLayout) -> None:
        """Add short prompt cards that populate the message field."""
        row = QHBoxLayout()
        row.setSpacing(12)
        suggestions = (
            (
                "Understand this project",
                "Get a guided codebase overview",
                "Summarize this project.",
            ),
            (
                "Plan a feature",
                "Break an idea into clear steps",
                "Help me plan a feature.",
            ),
            (
                "Find and fix a bug",
                "Share an error or describe an issue",
                "Help me debug an issue.",
            ),
        )
        for title, description, prompt in suggestions:
            card = SuggestionCard(title, description, prompt)
            card.prompt_selected.connect(self.set_prompt)
            row.addWidget(card, 1)
        layout.addLayout(row)

    def _build_transcript(self) -> None:
        """Create the scrollable conversation transcript area."""
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setVisible(False)
        self._transcript = QPlainTextEdit()
        self._transcript.setObjectName("transcript")
        self._transcript.setReadOnly(True)
        self._transcript.setAccessibleName("Conversation messages")
        self._scroll.setWidget(self._transcript)
        self.content_layout.addWidget(self._scroll, 1)

    def _build_composer(self) -> None:
        """Create the message input, task status, and send action."""
        composer = QFrame(objectName="composer")
        layout = QVBoxLayout(composer)
        layout.setContentsMargins(14, 8, 14, 10)
        self._prompt = QLineEdit()
        self._prompt.setObjectName("prompt")
        self._prompt.setPlaceholderText("Message Amethyst…")
        self._prompt.setAccessibleName("Message Amethyst")
        self._prompt.returnPressed.connect(self._submit_prompt)
        layout.addWidget(self._prompt)
        layout.addLayout(self._build_composer_actions())
        self.content_layout.addWidget(composer)

    def _build_composer_actions(self) -> QHBoxLayout:
        """Build composer actions and the visible task-state indicator."""
        actions = QHBoxLayout()
        add_context = QPushButton("＋  Add context")
        add_context.setObjectName("recent")
        add_context.setAccessibleName("Add context to the message")
        add_context.setEnabled(False)
        actions.addWidget(add_context)
        actions.addStretch(1)
        self._status = QLabel("Ready")
        self._status.setObjectName("statusPill")
        self._status.setAccessibleName("Task status")
        actions.addWidget(self._status)
        self._send = QPushButton("Send  ↑")
        self._send.setObjectName("send")
        self._send.setAccessibleName("Send message")
        self._send.clicked.connect(self._submit_prompt)
        actions.addWidget(self._send)
        return actions

    def set_prompt(self, prompt: str) -> None:
        """Populate and focus the composer from a suggestion card."""
        self._prompt.setText(prompt)
        self._prompt.setFocus()

    def submit_message(self) -> None:
        """Submit the current message through the application boundary."""
        self._submit_prompt()

    def _submit_prompt(self) -> None:
        """Validate the prompt locally and emit it to the window controller."""
        text = self._prompt.text().strip()
        if text and self._send.isEnabled():
            self.message_submitted.emit(text)

    def prepare_task(self, message: str) -> None:
        """Show a user message and prepare an empty streamed assistant reply."""
        self._welcome.hide()
        self._scroll.show()
        self._transcript.appendPlainText(f"YOU\n{message}\n")
        self._transcript.appendPlainText("AMETHYST · S0 DEVELOPMENT FAKE\n")
        self._assistant_text = ""
        self._prompt.clear()
        self._send.setEnabled(False)
        self.set_status("Starting…")

    def render_event(self, event: TaskEvent) -> None:
        """Render one typed S0 event without interpreting it as authorization."""
        payload = event.payload
        if isinstance(payload, TaskStateChanged):
            self.set_status(self._status_text(payload.status))
        elif isinstance(payload, TextDelta):
            self._append_text(payload.text)
        elif isinstance(payload, TaskFailure):
            self._transcript.appendPlainText(f"\nTask failed: {payload.message}")
        elif isinstance(payload, ToolResult):
            self._append_tool_result(payload)
        elif isinstance(payload, ApprovalRequest):
            self._append_approval_notice(payload)

    def _append_text(self, text: str) -> None:
        """Append a text delta and scroll the transcript to its latest content."""
        self._assistant_text += text
        self._transcript.insertPlainText(text)
        self._transcript.ensureCursorVisible()

    def _append_tool_result(self, result: ToolResult) -> None:
        """Show a tool result and preserve its explicit truncation state."""
        suffix = " (truncated)" if result.truncated else ""
        self._transcript.appendPlainText(f"\nTool result{suffix}: {result.content}")

    def _append_approval_notice(self, request: ApprovalRequest) -> None:
        """Show that listed actions need approval without granting them."""
        count = len(request.actions)
        self._transcript.appendPlainText(f"\nApproval required for {count} action(s).")

    def set_status(self, status: str) -> None:
        """Update the visible state label for the active task."""
        self._status.setText(status)

    def set_busy(self, busy: bool) -> None:
        """Disable or re-enable message submission while a task runs."""
        self._send.setEnabled(not busy)

    def render_error(self, message: str) -> None:
        """Display a safe application-service error in the transcript."""
        self._transcript.appendPlainText(f"\nUnable to start task: {message}")

    def focus_prompt(self) -> None:
        """Return keyboard focus to the message field after task completion."""
        self._prompt.setFocus()

    def reset(self) -> None:
        """Clear the transient transcript and return to the welcome screen."""
        self._assistant_text = ""
        self._transcript.clear()
        self._scroll.hide()
        self._welcome.show()
        self._prompt.clear()
        self.set_status("Ready")

    @staticmethod
    def _status_text(status: TaskStatus) -> str:
        """Map contract states to short labels suitable for the status pill."""
        return {
            TaskStatus.PENDING: "Pending",
            TaskStatus.RUNNING: "Running",
            TaskStatus.AWAITING_APPROVAL: "Awaiting approval",
            TaskStatus.PAUSED_FOR_BUDGET: "Paused for budget",
            TaskStatus.COMPLETED: "Completed",
            TaskStatus.CANCELLED: "Cancelled",
            TaskStatus.FAILED: "Failed",
        }[status]
