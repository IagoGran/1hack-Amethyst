# Frontend Development

## Frontend Stack

Framework: `Pending`. Approved product interface: a local, single-user desktop application with its own standalone window, not a browser interface. Support Ubuntu 24.04 LTS on x86-64 and Windows 11 through WSL2.

MVP workflows include chat, unified settings, task status, reviewed-diff approvals, sandboxed command/test results, and viewing/resuming/deleting conversations. Conversations persist locally until deleted. Diagnostic-log controls must allow explicit permanent saving of selected redacted logs; ordinary logs expire after seven days.

## Directory Structure

Current location and structure: `Pending`.

## Local Development

Command: `Pending`.

## Build

Command: `Pending`.

## Environment Variables

See `.ai-context/ENVIRONMENT.md`. Frontend-specific variables: `Pending`.

## Integration Points

### APIs

The logical boundary is `amethyst.ports.application.ApplicationService`, with async calls and sequenced task-event streams. `FakeApplicationService` in `adapters/fakes.py` supports independent UI development. Repositories and `ApprovalService` are separate ports; the approval placeholder always denies execution. See `docs/s0_contract_baseline.md` for call/event semantics. GUI event-loop bridge, transport, and process topology: `Pending`.

### Authentication

Remote/multi-user authentication is outside the approved initial deployment scope. Any local authentication design: `Pending`.

### Assets

`Pending`.

## Debugging

Tools and workflow: `Pending`.

## Frontend-Specific Conventions

See `.ai-context/CONVENTIONS.md`; interface-specific rules: `Pending`.

Approval controls must identify the exact action or listed batch/diffs, require renewed approval after changes, and expose permission revocation. Display token-budget pauses and allow an explicit budget increase. Distinguish truncated results and timeout outcomes from successful completion. Approved p95 targets are 200 ms for UI status feedback, 10 seconds for first visible model token, and 120 seconds for a typical task under the benchmark conditions in requirements section 5.5.

## Frontend Change Checklist

- [ ] Clearly represent execution, budget pause, cancellation, error, and approval states.
- [ ] Support keyboard navigation and accessible labels (NFR-16).
- [ ] Do not display an action as complete when it is not.
- [ ] Cover primary desktop workflows in smoke tests on Ubuntu and Windows/WSL2.
- [ ] Update context when the interface contract changes.
