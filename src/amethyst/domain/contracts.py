"""Vendor-neutral values shared by the desktop, application, and adapters.

Payloads may contain user content: these objects must not be logged wholesale.
Serialization and durable storage formats are deliberately not selected here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from amethyst.domain.tasks import TaskStatus

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)


class ErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    AUTHENTICATION = "authentication"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONFLICT = "conflict"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True)
class Usage:
    """Per-request token use and cumulative task budget accounting."""

    input_tokens: int = 0
    output_tokens: int = 0
    task_total_tokens: int = 0
    task_remaining_tokens: int = 0


class ContractError(Exception):
    """Boundary failure; message must be safe for display and contain no secrets.

    Transient is a hint, never permission to repeat a mutation or uncertain command.
    Unknown usage is None, not zero; the application must account conservatively.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        transient: bool = False,
        retry_after_seconds: float | None = None,
        usage: Usage | None = None,
    ) -> None:
        """Create a display-safe boundary failure with retry and usage metadata.

        Parameters
        ----------
        code : ErrorCode
            Stable boundary error classification.
        message : str
            Display-safe text associated with the operation.
        transient : bool
            Whether the failure may permit a safe retry.
        retry_after_seconds : float | None
            Optional provider-requested delay before a safe retry.
        usage : Usage | None
            Observed provider usage, or None when unknown.

        Returns
        -------
        None
        """
        super().__init__(message)
        self.code = code
        self.transient = transient
        self.retry_after_seconds = retry_after_seconds
        self.usage = usage


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class Source:
    identifier: str
    title: str = ""
    url: str | None = None


@dataclass(frozen=True, slots=True)
class OperationContext:
    """IDs and remaining limits for one call; not proof of authorization.

    Application owns budget/deadline accounting. Adapters honor cancellation and
    this remaining timeout; they must not silently retry.
    """

    task_id: str
    session_id: str
    timeout_seconds: float = 30.0
    output_limit_bytes: int = 1_048_576


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, JsonValue] = field(default_factory=dict)
    read_only: bool = True


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    content: str
    sources: tuple[Source, ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    streaming: bool
    tool_calls: bool
    context_tokens: int


@dataclass(frozen=True, slots=True)
class ModelRequest:
    model_id: str
    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...] = ()
    max_input_tokens: int = 32_000
    max_output_tokens: int = 8_000
    idle_timeout_seconds: float = 60.0
    total_timeout_seconds: float = 300.0


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ModelCompleted:
    """Exactly one final item per successful stream; usage is not incremental."""

    usage: Usage | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: Literal["stop", "tool_calls", "length"] = "stop"


type ModelEvent = TextDelta | ModelCompleted


@dataclass(frozen=True, slots=True)
class FileChange:
    """Workspace-relative path, displayed diff, and hash of the reviewed base.

    base_sha256=None means a proposed new file which must still be absent.
    """

    path: str
    diff: str
    base_sha256: str | None


@dataclass(frozen=True, slots=True)
class ProposedAction:
    """Fingerprint binds the entire payload, scope, diffs, and base file state."""

    id: str
    tool_name: str
    summary: str
    resource_scope: tuple[str, ...]
    fingerprint: str
    changes: tuple[FileChange, ...] = ()
    high_impact: bool = False


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: str
    task_id: str
    session_id: str
    actions: tuple[ProposedAction, ...]

    def __post_init__(self) -> None:
        """Reject empty approval batches and duplicate action identifiers.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if not self.actions or len({a.id for a in self.actions}) != len(self.actions):
            raise ValueError(
                "An approval must list distinct actions and cannot be empty."
            )


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"
    CONSUMED = "consumed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class Approval:
    request: ApprovalRequest
    status: ApprovalStatus = ApprovalStatus.PENDING
    consumed_action_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StartTask:
    conversation_id: str
    request: str
    model_connection_id: str
    skill_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskStateChanged:
    status: TaskStatus
    message: str = ""


@dataclass(frozen=True, slots=True)
class TaskFailure:
    code: ErrorCode
    message: str


type TaskEventPayload = (
    TaskStateChanged | TextDelta | ToolResult | ApprovalRequest | Usage | TaskFailure
)


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Per-task sequence starts at 1 and supports replay and deduplication."""

    task_id: str
    sequence: int
    payload: TaskEventPayload


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    title: str
    messages: tuple[Message, ...] = ()


@dataclass(frozen=True, slots=True)
class Skill:
    id: str
    name: str
    instructions: str
    enabled: bool = True
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class Connection:
    """Non-secret settings only; credential_ref is an opaque lookup key.

    Adapter-specific validation belongs to the configuration boundary. Never put
    credentials in options or endpoint URLs. This DTO alone does not sanitize
    untrusted configuration.
    """

    id: str
    kind: str
    options: dict[str, JsonValue] = field(default_factory=dict)
    enabled: bool = True
    credential_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectionHealth:
    available: bool
    message: str
    error_code: ErrorCode | None = None


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    """Container-only invocation; approval_id does not itself authorize execution.

    No host executable fallback is permitted. File mutations still require diff
    review; enabling execution requires explicit host and image validation.
    """

    action_id: str
    approval_id: str
    fingerprint: str
    workspace: Path
    argv: tuple[str, ...]
    working_directory: str = "."
    network_enabled: bool = False
    timeout_seconds: float = 120.0
    output_limit_bytes: int = 1_048_576


@dataclass(frozen=True, slots=True)
class SandboxResult:
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    outcome: Literal["completed", "cancelled", "timeout", "unknown"] = "completed"
    truncated: bool = False
