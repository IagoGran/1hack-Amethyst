# Workstream B Programmer Guide

This guide describes the implemented Workstream B application and security services, including Docker validation work on `feature/agent-security-docker-integration`. Workstream A (desktop UI) and Workstream C (live providers/connectors and durable persistence) remain separate.

## What the code provides

`amethyst.application.service.AgentService` implements the asynchronous `ApplicationService` port. It starts one task per conversation, reloads conversation messages, applies enabled and explicitly selected skills, streams model output as sequenced events, dispatches registered tools, waits for exact-action approval, checks tool results, and saves conversation snapshots through the repository port. Tasks report progress, approval waits, budget pauses, cancellation, completion and failure. A cancellation request waits for the model/tool operation to stop before acknowledging cancellation. Failures use safe, redacted messages.

`amethyst.security.permissions` supplies session-scoped read grants and an `ApprovalEngine`. Read grants identify a tool and a resource, can be inspected or revoked, and end with the session. Protected proposals enumerate actions and resource scopes. Approval consumption checks the active task and session, action membership, reviewed fingerprint and prior consumption; actions expire at task completion and pending session grants expire on session exit. `fingerprint` creates a SHA-256 digest of canonical JSON. Callers must include every security-relevant part of an operation in the canonical payload.

`amethyst.security.workspace.Workspace` reads explicitly permitted UTF-8 workspace files and prepares file edits as unified diffs. It rejects absolute paths, traversal, `.git`, symlinks, special files, multiply-linked files and oversized content. Edits are recomputed against current file contents and metadata, compared with the stored reviewed action, and applied only after approval consumption. Writes use a temporary sibling and atomic replacement; new files use a no-overwrite link. Deletions are marked high impact.

`amethyst.application.limits` and `amethyst.configuration.limits.Limits` enforce the documented defaults for task/model/tool/command deadlines, token budgets, retrieval and SQL result counts, output bytes, and retry count. Budget exhaustion pauses before another model request; an explicit positive increase resumes the task. The task deadline stops counting during approval waits. Retries require a transient provider/tool failure and a safe read-only operation with a session grant. SQL admission rejects known write or unsafe constructs; a production SQL adapter must also use database-enforced read-only transactions and credentials.

`amethyst.security.sandbox.DockerSandbox` uses Docker Engine/runc and an image pinned by digest. It mounts only the approved workspace read-only, denies network access by default, drops capabilities, enables `no-new-privileges`, applies resource limits, bounds output, and removes the container after completion, timeout or cancellation. It rejects image-declared volumes, disables image health checks and daemon output logging, requires confirmed terminal state, and waits for cleanup even after repeated cancellation. The runtime must be explicitly enabled after host validation. No host-command fallback exists. Write commands cannot modify the workspace; file changes go through `Workspace` and reviewed diffs. See [runtime profile and acceptance](sandbox_runtime.md).

`amethyst.security.credentials.OSCredentialStore` uses Linux Secret Service when available, with an in-memory fallback. It does not select arbitrary keyring plugins or fall back to plaintext files. `Redactor` and `StreamRedactor` remove known credentials and common token/password patterns before messages and output are persisted or emitted. `DiagnosticStore` accepts only enumerated operational metadata, expires unsaved records after seven days, and supports explicit permanent save/delete. `TaskTemporaryData` removes only directories it created.

## How to compose and use it

The UI or application bootstrap creates a shared session ID, `ApprovalEngine`, `PermissionService`, conversation repository, provider bindings, optional tool bindings and settings, then constructs `AgentService`:

```python
from amethyst.adapters.fakes import InMemoryRepository
from amethyst.application.service import AgentService, ProviderBinding
from amethyst.domain.contracts import Conversation, StartTask
from amethyst.security.permissions import ApprovalEngine, PermissionService

session_id = "app-session-id"
approvals = ApprovalEngine(session_id)
permissions = PermissionService(session_id)
conversations = InMemoryRepository[Conversation]()
service = AgentService(
    session_id=session_id,
    providers={"model-connection": ProviderBinding(provider, "model-id")},
    conversations=conversations,
    approvals=approvals,
    permissions=permissions,
    tools=(),
)
task = await service.start_task(
    StartTask("conversation-id", "Review this change", "model-connection")
)
async for event in service.events(task.id):
    if isinstance(event.payload, ApprovalRequest):
        # Present exactly the listed action and diff, then pass the user's choice.
        await approvals.decide(event.payload.id, granted=user_approved)
    else:
        render(event)
await service.close()
```

The Python package requires Python 3.13+. Install development dependencies with `uv sync --group dev`; run the CLI with `uv run 1hack-amethyst`. The current CLI is still a provisional startup. Build with `uv build`. The application service is an in-process async interface; Workstream A must bridge it to the desktop event loop. Its provider, repository, skill, and tool dependencies are injected so Workstream C can supply adapters without coupling them to the agent.

Register tools as `ToolBinding(tool, resource, kind="text", enabled=True)`. Supported structured result kinds are `sql` (JSON object with a `rows` array) and `retrieval` (JSON object with `chunks`; each chunk has string `content`). Read-only tool access requires a session grant or a one-action approval. Non-read-only tools always require explicit approval. Built-in `workspace.read`, `workspace.edit`, and `sandbox.run` tools are added only when their dependencies are configured.

Read file access requires `permissions.grant("workspace.read", str(workspace_root), recursive=True)`. Callers should expose grant/inspect/revoke and approval decisions as trusted user controls; model tools must never invoke them. Read grants expire when the app calls `AgentService.close()`.

## Tests and checks

Workstream B unit tests cover application, permissions, limits, retention, sandbox policy, and subprocess transport. `tests/integration/test_agent_sandbox.py` verifies application/approval/provider handoff with a daemon double. `test_live_sandbox.py` adds explicitly configured real-container acceptance and never contacts Docker during the default test run. The last full run passed 103 tests, skipped three opt-in live tests, and reported 88.79% branch coverage (309/348 branches) over `domain/`, `application/`, and `security/`. Ruff, mypy and a package build also passed. Re-run with:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest --cov --cov-report=term-missing --cov-report=json:/tmp/amethyst-coverage.json
uv build
```

## Integration boundaries and outstanding validation

- The current conversation repository is injected. Production retention across restarts, migrations and deletion coordination depend on Workstream C's durable repositories.
- Provider settings/secret references and live connectors depend on Workstream C. The application accepts provider/tool bindings; it does not implement vendor SDK adapters.
- Workstream A must expose user controls for permissions, approval decisions, cancellation and explicit budget increases, and display progress, truncation and terminal outcomes.
- Docker is disabled until its image, daemon and runtime policy are configured and validated. The real-container suite and profile are ready; execute the documented commands on both target configurations and retain the JUnit environment/results report.
- This implementation environment is Ubuntu 22.04.5, not the approved Ubuntu 24.04 x86-64 or Windows 11/WSL2 targets. Docker socket access is denied here. Live sandbox and credential-store behavior still require platform acceptance testing. A/C handoff expectations are in `tests/integration/README.md`.
- The read-only SQL validator is a conservative admission filter, not a substitute for connector-side database permissions. Query dialects and side-effecting functions require adapter-specific tests.
- Python function length and Numpydoc cleanup was requested separately and is not complete yet. Several application methods still exceed 100 lines, and most functions do not yet have Numpydoc docstrings.
