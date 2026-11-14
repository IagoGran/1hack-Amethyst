# Code structure and maintenance

The application has one supported desktop entry point: `uv run 1hack-amethyst`, also available through `uv run python -m amethyst`. Runtime services use the persistent Qt worker loop. The A1/A2/A3 previews, their launchers, sample records, preview-only repositories/workers, obsolete `src/main.py` launcher, and empty `src/llm/agent.py` have been removed. Shared transcript widgets now live in production UI modules.

## Responsibilities

| Area | Responsibility and main modules |
|---|---|
| `domain/` | Immutable requests, results, events, and task states. Terminal states and display labels have one definition. |
| `ports/` | Structural boundaries for application, models, tools, credentials, approval, storage, and sandboxing. The generic `Repository` contract supplies common CRUD semantics. |
| `application/service.py` | Session/task orchestration, PydanticAI run lifecycle, event publication, cancellation, and finalization. |
| `application/pydantic_agent.py` | PydanticAI agent/tool registration, provider-port bridge, and chat-history conversion. All registered tools execute through `ToolDispatcher`. |
| `application/state.py` | Provider/tool bindings and task-local execution state. |
| `application/model_execution.py` | Request capacity checks, streamed model events, token accounting, budget pauses, and safe retries. |
| `application/tool_dispatch.py` | Available tool schemas, exact proposals, approval waits, permission rechecks, connector dispatch, and sandbox/workspace handoff. |
| `application/budgets.py`, `timing.py`, `limits.py` | Token accounting, task/approval timing, retry rules, and bounded result policies. Existing `limits` imports remain compatible. |
| `configuration/` | Independent model/tool validators and factories, immutable connection metadata, operational limits, and settings persistence. |
| `adapters/models/` | Shared `ModelAdapter` setup, stream deadlines and function declarations; chat-completion and Gemini protocols in separate modules. `providers.py` retains the public provider exports. |
| `adapters/tools/` | Common `Tool` execution role and retrieval result handling; `ReadOnlySQLTool` shares SQL admission/schema/result behavior while each driver retains database-enforced protection. Vector adapters retain their family-specific shared implementation. |
| `adapters/persistence.py`, `codecs.py` | Generic durable SQLite repositories and domain-record serialization. Saved connection/conversation schemas remain compatible. |
| `adapters/http.py`, `serialization.py` | Shared retry-header parsing and linear, UTF-8-aware JSON record bounding. Each examined record is encoded once; callers own record limits and attribution. |
| `security/` | Separate permission/approval policy, approval lookup, credential storage, redaction, SQL admission, reviewed workspace edits, diagnostics, and container policy/transport. |
| `skills/selection.py` | Explicit and literal-condition skill selection, independent of model generation. |
| `ui/` | Desktop coordination, persistent worker, conversation/message components, composer, connection editors, permissions/diagnostics page, skills, limits, sidebar, and theme. |
| `tests/support/` | Deterministic fake services, disabled/deny-all adapters, and vendor fixtures. These are used by tests and are excluded from the application package. |

## Shared behavior and compatibility

Use inheritance for stable shared roles: `ModelAdapter`, `Tool`, `ReadOnlySQLTool`, `ApprovalStore`, `AsyncThread`, `ComposerPage`, and `ConnectionEditor`. Keep provider protocols, database enforcement, and authorization decisions explicit. PydanticAI owns iterative tool orchestration. Its provider bridge delegates each model request to `ModelRunner`, and every registered tool delegates to `ToolDispatcher`; model adapters request calls but never execute tools.

Do not copy schemas, terminal-state sets, codec logic, stream deadlines, source alignment, or byte-truncation loops into new integrations. Extend the existing implementation appropriate to the responsibility. See [model and tool architecture](integration_architecture.md) for the built-in integration workflow. Dynamic plugin registration remains Pending.

Stored connection kinds, credential references, SQLite schemas, task/event contracts, authorization lifetimes, default limits, and the container-only execution boundary are preserved. Selected public imports remain available where implementations moved. Test-only implementations now import from `tests.support`; preview import paths are intentionally removed.

## Removing unused code

Check production entry points, imports, public protocols, Qt signal connections, factory tables, and test references before removal. Interface methods invoked through a protocol and Qt callbacks are not dead merely because a simple text search finds no direct call. Tests legitimately own deterministic doubles; keep them outside `src/amethyst`.

The refactor used import reachability and private-name reference checks, followed by type checking, deterministic runtime tests, and package validation. These checks complement review; they do not prove arbitrary dynamic code unreachable. Live vendor, real-container, visible desktop, and performance acceptance remain Pending.

## Validation commands

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
QT_QPA_PLATFORM=offscreen uv run pytest
uv build
```

Run Linux-specific workspace and sandbox checks on Ubuntu/WSL. Opt-in real-container acceptance remains separately configured. All source and test functions follow the repository's Numpydoc convention and 100-line maximum. Shared offscreen Qt fixtures live in `tests/integration/conftest.py`.

Validation on 2026-11-14: 152 deterministic tests pass on WSL/Linux with three opt-in Docker checks skipped. Combined coverage is 93.09%; branch-only coverage is 313/364 (85.99%). Ruff, Linux-target mypy, source/wheel builds, and fresh extracted-wheel import/CLI/asset checks pass. Source/reference review finds no unreferenced private function names or repeated complete production function bodies; the wheel excludes previews and test-only support.
