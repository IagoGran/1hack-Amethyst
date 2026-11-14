# Frontend Development

## Frontend Stack

Production framework: `Pending`. Exploratory A1/A2/A3 previews in `src/amethyst/ui/` use PySide6; this does not select the production framework. Approved product interface: a local, single-user desktop application with its own standalone window, not a browser interface. Support Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2.

MVP workflows include chat, unified settings, task status, reviewed-diff approvals, sandboxed command/test results, and viewing/resuming/deleting conversations. Conversations persist locally until deleted. Diagnostic-log controls must allow explicit permanent saving of selected redacted logs; ordinary logs expire after seven days.

## Directory Structure

Exploratory preview: `src/amethyst/ui/`. Production interface structure: `Pending`.

## Local Development

Preview command: `PYTHONPATH=src python -m amethyst.ui.a3.preview_with_samples`, after installing PySide6 in the active environment. This A3 preview stores conversations locally and seeds fictional examples once. PySide6 is not yet declared in project dependency metadata.

## Build

Command: `Pending`.

## Environment Variables

See `.ai-context/ENVIRONMENT.md`. Frontend-specific variables: `Pending`.

## Integration Points

### APIs

The logical boundary is `amethyst.ports.application.ApplicationService`, with async calls and sequenced task-event streams. `FakeApplicationService` in `adapters/fakes.py` supports independent UI development. Repositories and `ApprovalService` are separate ports; the approval placeholder always denies execution. See `docs/s0_contract_baseline.md` for call/event semantics. A1/A2/A3 call the application port in worker threads; A3 also uses `ConversationRepository` through its preview-only local adapter. Production transport and process topology: `Pending`.

### Authentication

Remote/multi-user authentication is outside the approved initial deployment scope. Any local authentication design: `Pending`.

### Assets

The exploratory previews use `src/amethyst/ui/assets/amethyst-logo.png` for the transparent sidebar mark and native A3 window icon. Production branding and asset packaging: `Pending`.

## Debugging

Tools and workflow: `Pending`.

## Frontend-Specific Conventions

See `.ai-context/CONVENTIONS.md`; interface-specific rules: `Pending`.

In the A3 preview, the sidebar can be manually pinned open or collapsed to a narrow rail. An unpinned rail expands with a short eased animation on hover and collapses after the pointer leaves. The sidebar uses the purple accent palette with matching active navigation and chat highlights. Recent saved chats appear in a separate section, and all saved chats appear in a collapsible list that fills the remaining sidebar height and scrolls as needed; the open conversation is highlighted in both lists. Right-clicking a chat offers the existing confirmed delete workflow. Conversation history is no longer a separate navigation page. After a chat turn finishes, input focus returns to the message field.

Approval controls must identify the exact action or listed batch/diffs, require renewed approval after changes, and expose permission revocation. Display token-budget pauses and allow an explicit budget increase. Distinguish truncated results and timeout outcomes from successful completion. Approved p95 targets are 200 ms for UI status feedback, 10 seconds for first visible model token, and 120 seconds for a typical task under the benchmark conditions in requirements section 5.5.

## Frontend Change Checklist

- [ ] Clearly represent execution, budget pause, cancellation, error, and approval states.
- [ ] Support keyboard navigation and accessible labels (NFR-16).
- [ ] Do not display an action as complete when it is not.
- [ ] Cover primary desktop workflows in smoke tests on Ubuntu and Windows/WSL2.
- [ ] Update context when the interface contract changes.
