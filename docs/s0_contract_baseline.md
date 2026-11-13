# S0 Contract Baseline

## Scope and review status

This baseline implements the shared Python interfaces and development doubles for S0 in `implementation_plan.md`. It does not implement the MVP agent, GUI, live adapters, durable persistence, approval engine, or sandbox. Requirement scope remains defined by `project_requirements.md`.

The project owner instructed implementation on `feature/contracts` and a merge into `dev` after tests pass on 2026-11-13. `dev` is the integration branch. The three planned workstream branches are `feature/mvp-desktop`, `feature/mvp-agent-security`, and `feature/mvp-integrations`. Existing branches such as `feature/frontend` and `feature/agent-security` are preserved; they are not silently renamed or deleted.

The interfaces below are concrete, reviewable S0 proposals implemented as the development baseline. Separate acknowledgment from Iago, Hugo, and Antonio is **Pending**; implementation does not assert their approval. A hosted GitHub PR is **Pending** GitHub access. The owner-authorized local merge and branch synchronization are tracked in the S0 checklist. Do not describe a local merge as a hosted PR merge.

## Skeleton review

At the starting commit `e85472e`, the package contained a minimal `Task`, synchronous `ModelProvider.complete(prompt)` and `AgentTool.execute(input_data)` protocols, empty integration modules, and a print-only launcher. There was no persistence implementation, GUI, sandbox, or executable test suite. `src/llm/agent.py` was empty; it is left in place pending migration/removal.

The distribution and CLI remain `1hack-amethyst`. The Python package is now `amethyst` under `src/amethyst/`: the previous `1hack_amethyst` name could be loaded dynamically but could not appear in normal Python import syntax. `pyproject.toml` explicitly maps the distribution to the importable package. The CLI remains a clearly labeled provisional startup, not a desktop implementation.

## Contract proposals implemented in S0

| Boundary | Contract and data | Development implementation | Owner |
|---|---|---|---|
| Desktop/application | `ports/application.py`: start, inspect, cancel, increase budget, replay/follow task events | `FakeApplicationService` | A/B |
| Model | `ports/model_provider.py`: capabilities and asynchronous response stream | `FakeModelProvider` | C |
| Tool/connection health | `ports/tool.py`: definition, execute, test connection | `FakeTool` | B/C |
| Approval | `ports/approval.py`: request, decide, inspect, revoke, consume, task/session expiry | `DenyAllApprovalService` | B |
| Persistence | `ports/persistence.py`: conversation, skill, and connection repositories | Typed `InMemoryRepository` instances | C |
| Credentials | `ports/credentials.py`: opaque-reference get/set/delete | `MemoryCredentialStore` | B/C |
| Sandbox | `ports/sandbox.py`: container-only invocation | `DisabledSandbox` | B |

Shared values live in `domain/contracts.py`; task snapshots and status values live in `domain/tasks.py`. Ports depend on domain types and the standard library, with no vendor SDK, GUI, database, or container dependencies. No runtime dependency was added. Existing skeleton callers must migrate from the old synchronous protocols; there were no implemented consumers to preserve.

### Calls, events, errors, and cancellation

- Use Python async calls and async iterators as the logical boundary. A GUI must bridge these onto its event loop or a background loop without blocking its event thread. This does not choose a GUI framework, IPC transport, or process topology.
- `start_task` returns an ID-bearing snapshot promptly. Starting with an existing conversation ID means continuing that conversation; a new task receives a new ID. Explicit `skill_ids` and the configured model connection are carried in the request.
- Task statuses include pending, running, awaiting approval, paused for budget, completed, cancelled, and failed. Terminal states are completed/cancelled/failed. A timeout produces a safe failure event and failed state; it must not leave the task running.
- Task events have monotonically increasing per-task sequence numbers starting at 1. `events(after_sequence=N)` replays events after N and follows live events until terminal delivery. Multiple subscriptions must not start or repeat execution. Replay retention/storage across restart remains B1/C6 work; the fake retains events only in memory.
- The application emits a `TaskFailure` before a failed state. Text deltas, usage, tool results, and approval requests have typed event payloads. Cancellation is acknowledged only when further tool dispatch is blocked. Adapter operations use normal `asyncio` cancellation; production sandbox cancellation must stop the container before acknowledgment.
- `ContractError` carries a safe message, stable category, optional retry delay, and optional consumed model usage. Missing usage means unknown, not zero. Adapters translate vendor errors and do not silently retry. The application owns remaining deadlines, conservative usage accounting, and approved retry policy. A transient hint does not permit retrying an uncertain mutation/command.

### Providers and tools

- Model streaming emits zero or more `TextDelta` items and exactly one `ModelCompleted` on success. A non-streaming adapter emits its complete text as one delta. Completion carries whole-attempt usage, complete tool calls with stable IDs, and a finish reason; usage must not be counted once per delta. Tool calls are represented in subsequent assistant messages, and tool response messages carry the matching call ID.
- Capabilities are queried per model ID. Input plus reserved output must fit the model capacity. Request fields carry input/output and idle/total timeout limits; S0 does not enforce the complete B5 budget policy.
- Tool definitions contain a name, JSON argument schema, and read-only classification. Calls/results share a call ID. Results preserve available source identifiers/URLs and explicit truncation. The classification is metadata, not permission: B must check authorization before dispatch, and C must enforce read-only SQL at the connection boundary.
- `OperationContext` identifies task/session, remaining call timeout, and output byte limit. Model adapters use the lower of request and remaining context deadlines. Provider-specific connection testing implements `ConnectionTester`. Operation context IDs never grant access.

### Approvals and sandbox

- Approval proposals explicitly enumerate distinct actions, resource scopes, summaries, displayed file diffs, reviewed base hashes, and action fingerprints. `base_sha256=None` denotes a file that must remain absent until creation. Approval requests cannot be empty or repeat action IDs.
- Fingerprints must bind the full execution payload and scope, including diffs, file state, command arguments, workspace, and network scope where applicable. Canonical fingerprint encoding and race-free execution/file-state validation are **Pending** in B2/B3/B4; an opaque string in a DTO is not validation or authorization.
- `consume` must atomically validate approval state, action membership, task/session, current fingerprint/file state, and non-consumption before execution. Approval is consumed per listed action. Revocation blocks remaining batch actions; task completion/session exit expires outstanding approval. Session read-grant APIs remain B3 work.
- The deny-all placeholder never grants or consumes an approval successfully. It exposes denied/revoked/expired states for development and fails closed even if the caller supplies a matching fingerprint.
- Sandbox requests specify argument vectors, the approved workspace, relative working directory, network flag (false by default), and bounded timeout/output. They contain no host execution mode. Authorization IDs are references requiring validation, not bearer credentials.
- `DisabledSandbox` always raises `UNAVAILABLE` without running anything. Runtime choice, mount/path restrictions, network authorization, cancellation, and a staging policy that preserves reviewed-diff requirements are **Pending** in B4. S0 must never be used to execute commands on the host as a fallback.

### Persistence and credentials

- Repositories expose `save`, `load`, `list`, and `delete`: save upserts, missing load raises `NOT_FOUND`, list sorts by ID, and deletion is idempotent. Returned values are detached snapshots, including nested connection options and message tool-call arguments.
- Conversation records contain ordered messages; reopening a conversation loads its record and submits a new task using that ID. Skill records carry enabled state and optional condition text; condition grammar/evaluation remains B/C work. Connection records contain enabled state, non-secret options, and an opaque credential reference.
- In-memory repositories intentionally lose records on restart. They do not satisfy conversation/settings/skill retention. The durable engine, schema versioning, migrations, concurrent update strategy, encryption/backup design, and cleanup schedule remain **Pending** for C6/B6.
- Connection kinds/options are an extensible carrier, not validated provider configuration. C5 must define allowed kinds, validate endpoint/model/connection fields, and reject secrets in ordinary options and URLs. Adapter factories resolve credential references through `CredentialStore`; secrets never belong in `Connection` exports or diagnostic output.
- The memory credential double performs no disk I/O and can be cleared at shutdown. OS credential-store selection and fallback integration remain B6. No credential store is automatically wired into the CLI.

## Independent workstream usage

```python
from amethyst.adapters.fakes import FakeApplicationService, InMemoryRepository
from amethyst.domain.contracts import Conversation, StartTask
from amethyst.ports.application import ApplicationService
from amethyst.ports.persistence import ConversationRepository


async def preview() -> None:
    conversations: ConversationRepository = InMemoryRepository[Conversation]()
    await conversations.save(Conversation("example", "Example conversation"))
    application: ApplicationService = FakeApplicationService()
    task = await application.start_task(StartTask("example", "Hello", "fixture"))
    async for event in application.events(task.id):
        # Feed the typed payload into the desktop view model.
        pass
```

A can develop UI state against the fake service and repositories; B can implement orchestration and authorization behind the ports; C can implement adapters/repositories without importing GUI or security implementations. Fake application output is explicitly labeled and does not invoke tools, persist conversations, evaluate skills, or simulate budget increases. Do not wire development doubles as production integrations.

## Pending technology proposals

These are bounded follow-up proposals, not approved architecture:

| Decision | Proposed next evaluation | Owner / task | Status |
|---|---|---|---|
| GUI, packaging, WSL2 launch | Evaluate a Python-native standalone desktop shell and async bridge on both target platforms before selecting a framework | Iago / A1 | Pending |
| Container runtime and edit isolation | Compare available runtime support on Ubuntu/WSL2; demonstrate workspace/network isolation and staged diff review before selecting a profile | Hugo / B4 | Pending |
| Durable storage and maintenance | Evaluate a local embedded database behind these repositories, including migrations, atomic saves, deletion, and cleanup; external SQLite support does not select it | Antonio with Hugo / C6, B6 | Pending |
| Provider SDKs and model IDs | Select per adapter after validating streaming, usage, cancellation, and capability reporting against the ports | Antonio / C2–C5 | Pending |
| Benchmarks | Define reference machines/models and 30-run fixtures under requirements section 5.5 | A/B/C / A7, B7, C7 | Pending |

## Validation and integration procedure

Run `uv sync --locked --group dev`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src tests`, `uv run pytest`, and `uv build`. Check `uv run 1hack-amethyst` and `uv run python -m amethyst`; both remain provisional launchers. A fresh wheel installation must import `amethyst` and expose the CLI.

The S0 suite covers fake streams/results, replay and subscriber-independent completion, cancellation, detached repository snapshots, memory credentials, fail-closed approvals, and the disabled sandbox. These checks do not establish the MVP 80% branch-coverage gate, real adapter behavior, GUI platform acceptance, persistence after restart, or production enforcement.

After checks pass, commit the baseline on `feature/contracts`, merge it into `dev`, and create or fast-forward each planned workstream branch from `dev`. Never reset an existing divergent workstream branch; merge the baseline normally if needed. Hosted PR publication/review remains Pending until GitHub access is available. No feature implementation may depend on an unmerged workstream commit.
