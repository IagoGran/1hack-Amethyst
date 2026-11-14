# Workstream B Programmer Guide

This guide describes the implemented Workstream B application and security services, including Docker validation work on `feature/agent-security-docker-integration`. A/B/C are now composed by `DesktopRuntime` and the integrated PySide6 launcher; see [desktop integration](desktop_integration.md). The service-level examples below remain useful for non-UI callers.

## What the code provides

`amethyst.application.service.AgentService` implements the asynchronous `ApplicationService` port. It starts one task per conversation, reloads conversation messages, applies enabled and explicitly selected skills, streams model output as sequenced events, dispatches registered tools, waits for exact-action approval, checks tool results, and saves conversation snapshots through the repository port. Tasks report progress, approval waits, budget pauses, cancellation, completion and failure. A cancellation request waits for the model/tool operation to stop before acknowledging cancellation. Failures use safe, redacted messages.

`amethyst.security.permissions` supplies session-scoped read grants and an `ApprovalEngine`. Read grants identify a tool and a resource, can be inspected or revoked, and end with the session. Protected proposals enumerate actions and resource scopes. Approval consumption checks the active task and session, action membership, reviewed fingerprint and prior consumption; actions expire at task completion and pending session grants expire on session exit. `fingerprint` creates a SHA-256 digest of canonical JSON. Callers must include every security-relevant part of an operation in the canonical payload.

`amethyst.security.workspace.Workspace` reads explicitly permitted UTF-8 workspace files and prepares file edits as unified diffs. It rejects absolute paths, traversal, `.git`, symlinks, special files, multiply-linked files and oversized content. Edits are recomputed against current file contents and metadata, compared with the stored reviewed action, and applied only after approval consumption. Writes use a temporary sibling and atomic replacement; new files use a no-overwrite link. Deletions are marked high impact.

`amethyst.application.limits` and `amethyst.configuration.limits.Limits` enforce the documented defaults for task/model/tool/command deadlines, token budgets, retrieval and SQL result counts, output bytes, and retry count. Budget exhaustion pauses before another model request; an explicit positive increase resumes the task. The task deadline stops counting during approval waits. Retries require a transient provider/tool failure and a safe read-only operation with a session grant. SQL admission rejects known write or unsafe constructs; a production SQL adapter must also use database-enforced read-only transactions and credentials.

`amethyst.security.sandbox.DockerSandbox` uses Docker Engine/runc and an image pinned by digest. It mounts only the approved workspace read-only, denies network access by default, drops capabilities, enables `no-new-privileges`, applies resource limits, bounds output, and removes the container after completion, timeout or cancellation. It rejects image-declared volumes, disables image health checks and daemon output logging, requires confirmed terminal state, and waits for cleanup even after repeated cancellation. The runtime must be explicitly enabled after host validation. No host-command fallback exists. Write commands cannot modify the workspace; file changes go through `Workspace` and reviewed diffs. See [runtime profile and acceptance](sandbox_runtime.md).

`amethyst.security.credentials.OSCredentialStore` uses Linux Secret Service when available, with an in-memory fallback. It does not select arbitrary keyring plugins or fall back to plaintext files. `security.redaction.Redactor` and `StreamRedactor` remove known credentials and common token/password patterns before messages and output are persisted or emitted. `DiagnosticStore` accepts only enumerated operational metadata, expires unsaved records after seven days, and supports explicit permanent save/delete. `TaskTemporaryData` removes only directories it created.

## How to compose and use it

The UI or application bootstrap creates a shared session ID, `ApprovalEngine`, `PermissionService`, conversation repository, provider bindings, optional tool bindings and settings, then constructs `AgentService`:

```python
from amethyst.adapters.persistence import create_sqlite_repositories
from amethyst.application.service import AgentService, ProviderBinding
from amethyst.domain.contracts import Conversation, StartTask
from amethyst.security.permissions import ApprovalEngine, PermissionService

session_id = "app-session-id"
approvals = ApprovalEngine(session_id)
permissions = PermissionService(session_id)
conversations = create_sqlite_repositories().conversations
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

The Python package requires Python 3.13+. Install dependencies with `uv sync --group dev`; launch the integrated desktop with `uv run 1hack-amethyst`. Build with `uv build`. `DesktopWorker` bridges the in-process async service to Qt through one persistent worker loop and typed signals. Provider, repository, skill, and tool dependencies remain injected.

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

- `DesktopRuntime` injects C's durable conversation/skill/connection repositories; headless restart/resume/delete checks cover the desktop handoff. Migrations beyond version 1 remain Pending.
- The desktop resolves C's provider settings/secret references and adapters before each task. Connector aliases prevent collisions; retrieval results are normalized to B's structured result contract. Live vendor-service acceptance remains Pending.
- The integrated desktop exposes permissions, exact-action/diff approval, revocation, cancellation, explicit budget increases, progress, sources, truncation, diagnostics, and terminal outcomes.
- Docker is disabled until its image, daemon and runtime policy are configured and validated. The real-container suite and profile are ready; execute the documented commands on both target configurations and retain the JUnit environment/results report.
- Workstream B's original implementation environment was Ubuntu 22.04.5 with denied Docker socket access. Integrated deterministic checks now run under Ubuntu 24.04.3 WSL with Qt offscreen. Live sandbox, OS credential-store behavior, and visible desktop workflows still require platform acceptance testing. A/C handoff coverage and remaining expectations are in `tests/integration/README.md`.
- The read-only SQL validator is a conservative admission filter, not a substitute for connector-side database permissions. Query dialects and side-effecting functions require adapter-specific tests.
- The repository-wide refactor separates model execution, authorized tool dispatch, task state, budgets, timing, SQL admission, Docker transport, redaction, and record codecs. Source and test functions now follow Numpydoc and the 100-line limit. See `docs/code_structure.md`.
