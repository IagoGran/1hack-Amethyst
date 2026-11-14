# Frontend Development

## Frontend Stack

Framework: PySide6, declared in runtime dependencies. `ui/desktop.py` is the integrated local single-user standalone window. `ui/desktop_worker.py` owns one persistent asyncio loop; all real application calls and controls execute there. A1/A2/A3 previews and their launchers have been removed. Supported environments are Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2.

MVP workflows include chat, unified settings, task status, reviewed-diff approvals, sandboxed command/test results, and viewing/resuming/deleting conversations. Conversations persist locally until deleted. Diagnostic-log controls must allow explicit permanent saving of selected redacted logs; ordinary logs expire after seven days.

## Directory Structure

`src/amethyst/ui/`: `desktop.py` and `desktop_worker.py` compose the real shell and task bridge; connection, skill, and limits pages provide settings; shared sidebar/theme and production conversation/message/composer widgets supply the visual layout. Permissions and diagnostics use `permissions_page.py`. `application/runtime.py` composes backend services. See `docs/desktop_integration.md`.

## Local Development

Install with `uv sync --group dev`; launch with `uv run 1hack-amethyst` or `uv run python -m amethyst`. Configure the selected provider/model in Connections; normal launch uses no fake responses or fictional records. `--database`, `--workspace`, `--sandbox-image`, and `--enable-sandbox` are documented in `docs/desktop_integration.md`. Preview-only launchers, sample records, and their database adapter have been removed.

## Build

Build the Python wheel with `uv build`. Native installers remain `Pending`.

## Environment Variables

See `.ai-context/ENVIRONMENT.md`. Frontend-specific variables: `Pending`.

## Integration Points

Connections contains separate Models and Tools tabs backed by `ModelConnectionPage` and `ToolConnectionPage`, sharing `ConnectionEditor`. Category metadata and fields come from `configuration/catalog.py`. Each form lists only its category, preserves blank replacement secrets, and prevents overwriting a name owned by the other category. Operational limits remain separate. See `docs/integration_architecture.md`.

### APIs

The application boundary uses async calls and sequenced typed events. `DesktopRuntime` injects real `AgentService`, `ApprovalEngine`, `PermissionService`, configured model/tool adapters, and SQLite repositories. `DesktopWorker` dispatches task, repository, credential, and trusted security controls on one loop. Qt receives detached results through signals. Configuration changes and deletion are blocked during tasks; revocation and cancellation stay available. Test-only fake services live under `tests/support/`. See `docs/desktop_integration.md` and `docs/s0_contract_baseline.md`.

### Authentication

Remote/multi-user authentication is outside the approved initial deployment scope. Any local authentication design: `Pending`.

### Assets

The integrated window uses `src/amethyst/ui/assets/amethyst-logo.png` for the sidebar and window icon. The existing Python wheel backend includes package assets; native installer branding remains `Pending`.

## Debugging

Tools and workflow: `Pending`.

## Frontend-Specific Conventions

See `.ai-context/CONVENTIONS.md`; interface-specific rules: `Pending`.

In the desktop, the sidebar can be manually pinned open or collapsed to a narrow rail. An unpinned rail expands with a short eased animation on hover and collapses after the pointer leaves. The sidebar uses the purple accent palette with matching active navigation and chat highlights. Recent saved chats appear in a separate section, and all saved chats appear in a collapsible list that fills the remaining sidebar height and scrolls as needed; the open conversation is highlighted in both lists. Right-clicking a chat offers the existing confirmed delete workflow. Conversation history is no longer a separate navigation page. After a chat turn finishes, input focus returns to the message field.

Approval controls must identify the exact action or listed batch/diffs, require renewed approval after changes, and expose permission revocation. Display token-budget pauses and allow an explicit budget increase. Distinguish truncated results and timeout outcomes from successful completion. Approved p95 targets are 200 ms for UI status feedback, 10 seconds for first visible model token, and 120 seconds for a typical task under the benchmark conditions in requirements section 5.5.

## Frontend Change Checklist

- [ ] Clearly represent execution, budget pause, cancellation, error, and approval states.
- [ ] Support keyboard navigation and accessible labels (NFR-16).
- [ ] Do not display an action as complete when it is not.
- [ ] Cover primary desktop workflows in smoke tests on Ubuntu and Windows/WSL2.
- [ ] Update context when the interface contract changes.
