# Integrated desktop

The integration branch connects Workstreams A, B, and C through `DesktopRuntime`. The normal launcher now opens the PySide6 desktop with the real `AgentService` and SQLite repositories. Preview entry points, fictional sample records, and preview-only persistence have been removed. Shared conversation widgets are now production UI modules; deterministic doubles live only under `tests/support/`.

## Launch

Run on Ubuntu 24.04 or inside Ubuntu on Windows 11 WSL2 with GUI support:

```bash
uv sync --group dev
uv run 1hack-amethyst
# Equivalent:
uv run python -m amethyst
```

Use `--database /path/to/app.sqlite3` to isolate application data. The default remains `$XDG_DATA_HOME/amethyst/amethyst.sqlite3`, falling back to `~/.local/share/amethyst/amethyst.sqlite3`. Numeric settings use a sibling `amethyst.settings.json` (or the selected database basename with `.settings.json`). Diagnostics use the database directory's `diagnostics/` subdirectory. Secrets are stored through Linux Secret Service, with a disclosed memory-only fallback. Native Windows can run chat/settings but workspace and container operations require Linux/WSL2.

1. In **Connections → Models**, enter a name, provider, model ID, optional endpoint/context size, and masked API key. Save the connection, then choose it in Chat. Ollama needs a model ID and normally no secret. Blank replacement secrets preserve an existing credential reference.
2. Configure SQL, Brave, or vector connections in **Connections → Tools**. The model and tool tabs have separate lists and type choices; existing saved connections appear automatically in their category. Enable/disable changes apply after Save. Test checks the saved configuration. Install optional drivers with `uv sync --extra integrations`, or select the individual extras in `pyproject.toml`. Missing optional connectors produce a visible warning while chat remains available.
3. Select enabled skills in **Skills** to apply them to the next turn. An optional `contains:literal text` condition applies an enabled skill when that literal occurs in the request.
4. In **Permissions**, choose a workspace and explicitly grant session read access. Its path is displayed before granting. Grants can be revoked; action approvals show every action, resource scope, high-impact flag, and file diff. Closing the approval dialog denies it. Read-only SQL/search/vector calls require exact-action approval unless a corresponding session grant exists.
5. Use Cancel and the explicit token increase controls for active tasks. Task details display tool results, truncation, and source identifiers. Conversation resumption reloads persisted messages; the UI does not duplicate or pre-save the user turn.
6. The **Operational limits** tab saves validated numeric limits for subsequent tasks and across restarts. Diagnostic records expire after seven days unless explicitly saved permanently in Permissions.

## Container execution

Read [the Docker runtime profile](sandbox_runtime.md) and validate the host first. Provision the trusted image separately, then launch with explicit configuration:

```bash
uv run 1hack-amethyst --workspace /absolute/project \
  --sandbox-image trusted-image@sha256:YOUR_64_CHARACTER_DIGEST \
  --enable-sandbox
```

The bootstrap switch asserts completed host validation; it does not perform acceptance testing. Every command still requires review of its exact arguments, workspace, and network scope. The workspace is mounted read-only; file edits use the separately reviewed diff path. No host-command fallback exists. Without explicit sandbox configuration, command tools are unavailable. Workspace selection alone grants no file access.

## Composition

See [model and tool architecture](integration_architecture.md) for the independent validators/factories, shared connection catalog, adapter superclasses, and built-in extension workflow.

- `application/runtime.py` creates one shared agent/approval/permission session, opens credentials, injects durable repositories, resolves selected model settings, and registers enabled tools.
- Connector aliases derive from kind and connection ID, allowing multiple SQL/search/vector connections without native tool-name collisions. Aliases are translated back for adapter execution. Brave/vector list results are normalized to the agent's bounded `chunks`/`content` contract; SQL retains its `rows` contract.
- `ui/desktop_worker.py` owns one persistent asyncio loop on a Qt thread. All repository calls, approvals, cancellation, and budget operations run there. The UI receives detached results and typed task events via signals. Settings changes and deletion are blocked during a task. Permission revocation remains available.
- Shutdown cancels active tasks, waits for cleanup, expires session authorization, clears memory credentials, and only then closes the worker and window.
- PySide6 is a declared runtime dependency. A1/A2/A3 preview launchers have been removed. Python wheel packaging uses the existing uv backend; native installers remain Pending.

## Validation and remaining acceptance

Repository-wide refactor validation on 2026-11-14: WSL/Linux Python 3.13.18 and Qt offscreen pass 152 deterministic tests; three opt-in real-container tests skip. Combined coverage is 93.09%, with 313/364 branches covered (85.99%). Ruff lint/format, Linux-target mypy, wheel/source build, and fresh extracted-wheel import/CLI/PNG checks pass. Focused native-Windows settings, adapters, runtime, permissions, and desktop checks pass. The wheel excludes removed previews and test-only doubles. See [code structure](code_structure.md) for module boundaries and cleanup checks.

`tests/integration/test_desktop.py` runs real Qt widgets, the worker, agent, HTTP model/search adapters, and SQLite repositories against local deterministic HTTP fixtures. It covers approval/denial, selected skills, SQL/search results, restart/resumption/deletion, token pauses/increases, cancellation while awaiting approval, and shutdown during an active task. `tests/unit/test_runtime.py` adds credential isolation, settings retention, optional-connector degradation, and all three vector-result handoffs.

Headless checks use `QT_QPA_PLATFORM=offscreen`; they do not establish visible GUI behavior, accessibility, latency, or live vendor compatibility. Live model/data-service checks, real Docker acceptance, native Ubuntu desktop smoke, visible WSLg smoke, performance benchmarks, and OS credential-store acceptance remain Pending. Natural-language query embedding remains Pending; vector tools currently require explicit numeric vectors. Encryption, backup design, and native installers remain Pending. Overall MVP acceptance is not claimed.

Earlier integration baseline: Ubuntu 24.04.3 under WSL, x86-64, Python 3.13.18, Qt offscreen passed 124 tests without warnings; three explicitly configured real-Docker tests skipped. Its branch-only coverage was 327/384 (85.16%), with 92.32% combined coverage. The refactor validation above supersedes these test/coverage counts. Linux-specific workspace and Docker checks must run inside WSL. SQLite repository operations close each connection deterministically after commit/rollback, with a handle-closure regression test.
