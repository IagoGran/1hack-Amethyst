"""Run the configured Amethyst agent in a terminal for local diagnosis."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from amethyst.application.runtime import DesktopRuntime
from amethyst.configuration.catalog import MODEL_KINDS
from amethyst.domain.contracts import (
    ApprovalRequest,
    Connection,
    ContractError,
    ErrorCode,
    StartTask,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
    ToolResult,
    Usage,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.security.redaction import Redactor


def _parser() -> argparse.ArgumentParser:
    """Build command-line options for the terminal client.

    Parameters
    ----------
    None

    Returns
    -------
    argparse.ArgumentParser
        Parser for the terminal client options.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Model connection ID")
    parser.add_argument("--workspace", type=Path, help="Workspace path for file tools")
    parser.add_argument("--database", type=Path, help="Amethyst SQLite database path")
    return parser


def _display_error(error: BaseException, redactor: Redactor) -> None:
    """Print a redacted error with a useful recovery hint when available.

    Parameters
    ----------
    error : BaseException
        Error raised by setup or terminal interaction.
    redactor : Redactor
        Session redactor used to hide known credentials.

    Returns
    -------
    None
    """
    print("\n[Error]")
    current: BaseException | None = error
    for _ in range(4):
        if current is None:
            break
        message = redactor.redact(str(current)).strip()
        if isinstance(current, ContractError):
            print(f"{current.code.value}: {message or 'No details provided.'}")
            hint = _error_hint(current.code)
            if hint:
                print(f"Next step: {hint}")
        else:
            print(f"{type(current).__name__}: {message or 'No details provided.'}")
        current = current.__cause__ or current.__context__


def _error_hint(code: ErrorCode) -> str | None:
    """Return a concise recovery hint for common agent failures.

    Parameters
    ----------
    code : ErrorCode
        Stable error code associated with a contract failure.

    Returns
    -------
    str or None
        Actionable hint, if one applies.
    """
    hints = {
        ErrorCode.PERMISSION_DENIED: (
            "Grant read access to the requested workspace path. For a protected "
            "write, approve its exact proposal when prompted."
        ),
        ErrorCode.NOT_FOUND: (
            "Check the workspace-relative path and list its parent folder."
        ),
        ErrorCode.INVALID_INPUT: (
            "Check the requested path, file content, or tool arguments."
        ),
        ErrorCode.UNAVAILABLE: (
            "Check that the selected model, connector, or sandbox is enabled."
        ),
        ErrorCode.TIMEOUT: (
            "Retry with a smaller request or increase the relevant timeout."
        ),
        ErrorCode.CONFLICT: (
            "Inspect the current file or directory state, then submit a fresh request."
        ),
        ErrorCode.AUTHENTICATION: "Check the configured connection credentials.",
        ErrorCode.BUDGET_EXHAUSTED: "Increase the task token budget to continue.",
    }
    return hints.get(code)


async def _select_model(
    runtime: DesktopRuntime, requested: str | None
) -> Connection | None:
    """Select an enabled model from the saved connection catalog.

    Parameters
    ----------
    runtime : DesktopRuntime
        Open application runtime.
    requested : str or None
        Optional connection ID.

    Returns
    -------
    Connection or None
        Selected model connection, if available.
    """
    models = tuple(
        connection
        for connection in await runtime.connections.list()
        if connection.enabled and connection.kind in MODEL_KINDS
    )
    if requested:
        return next(
            (model for model in models if requested == model.id),
            None,
        )
    if len(models) == 1:
        return models[0]
    if not models:
        print("No enabled model connections found. Configure one in Amethyst first.")
        return None
    print("Enabled model connections:")
    for index, model in enumerate(models, start=1):
        model_id = model.options.get("model_id", "unknown model")
        print(f"  {index}. {model.id} ({model.kind}: {model_id})")
    selection = input("Choose a model by number or connection ID: ").strip()
    if selection.isdigit() and 1 <= int(selection) <= len(models):
        return models[int(selection) - 1]
    return next((model for model in models if model.id == selection), None)


async def _configure_workspace(runtime: DesktopRuntime, path: Path) -> None:
    """Select a workspace and request an explicit recursive read grant.

    Parameters
    ----------
    runtime : DesktopRuntime
        Open application runtime.
    path : pathlib.Path
        Workspace selected by the user on the command line.

    Returns
    -------
    None
    """
    runtime.set_workspace(path)
    root = runtime.agent.workspace.root
    print(f"Workspace: {root}")
    answer = input("Allow reading files under this directory? [y/N] ").strip()
    if answer.casefold() in {"y", "yes"}:
        runtime.agent.permissions.grant("workspace.read", str(root), recursive=True)
        print("Workspace read access granted for this terminal session.")
    else:
        print("Workspace read access was not granted.")


async def _approve(runtime: DesktopRuntime, proposal: ApprovalRequest) -> None:
    """Display proposed actions and apply the user's terminal decision.

    Parameters
    ----------
    runtime : DesktopRuntime
        Open application runtime.
    proposal : ApprovalRequest
        Exact actions awaiting user approval.

    Returns
    -------
    None
    """
    print("\n[Approval required]")
    for action in proposal.actions:
        print(f"- {action.tool_name}: {action.summary}")
        for scope in action.resource_scope:
            print(f"  Scope: {scope}")
        for change in action.changes:
            print(f"  Diff for {change.path}:\n{change.diff}")
    answer = input("Approve these exact actions? [y/N] ").strip().casefold()
    await runtime.agent.approvals.decide(proposal.id, granted=answer in {"y", "yes"})


async def _increase_budget(runtime: DesktopRuntime, task_id: str) -> None:
    """Ask before resuming a task paused at its token limit.

    Parameters
    ----------
    runtime : DesktopRuntime
        Open application runtime.
    task_id : str
        Active task identifier.

    Returns
    -------
    None
    """
    answer = input("Task budget exhausted. Add tokens to continue? [amount/N] ").strip()
    if answer.isdigit() and int(answer) > 0:
        await runtime.agent.increase_budget(task_id, int(answer))


async def _print_events(runtime: DesktopRuntime, task_id: str) -> None:
    """Print streamed output, tool results, approvals, and task errors.

    Parameters
    ----------
    runtime : DesktopRuntime
        Open application runtime.
    task_id : str
        Active task identifier.

    Returns
    -------
    None
    """
    print("Amethyst: ", end="", flush=True)
    async for event in runtime.agent.events(task_id):
        payload = event.payload
        if isinstance(payload, TextDelta):
            print(payload.text, end="", flush=True)
        elif isinstance(payload, ToolResult):
            print(f"\n\n[Tool result]\n{payload.content}")
            if payload.truncated:
                print("[Tool output was truncated]")
        elif isinstance(payload, ApprovalRequest):
            await _approve(runtime, payload)
        elif isinstance(payload, TaskFailure):
            print(f"\n[Error: {payload.code.value}] {payload.message}")
            hint = _error_hint(payload.code)
            if hint:
                print(f"Next step: {hint}")
        elif isinstance(payload, Usage):
            print(
                f"\n[Token budget: {payload.task_total_tokens} used, "
                f"{payload.task_remaining_tokens} remaining]"
            )
        elif isinstance(payload, TaskStateChanged):
            print(f"\n[{payload.status.value}] {payload.message}")
            if payload.status == TaskStatus.PAUSED_FOR_BUDGET:
                await _increase_budget(runtime, task_id)
    print()


async def _chat(args: argparse.Namespace) -> None:
    """Open the local runtime and run an interactive terminal chat.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line options.

    Returns
    -------
    None
    """
    runtime: DesktopRuntime | None = None
    redactor = Redactor()
    try:
        runtime = await DesktopRuntime.open(args.database)
        if args.workspace:
            await _configure_workspace(runtime, args.workspace)
        model = await _select_model(runtime, args.model)
        if model is None:
            print("No matching enabled model. Check the connection ID and try again.")
            return
        await runtime.configure(model.id)
        for warning in runtime.warnings:
            print(f"[Warning] {redactor.redact(warning)}")
        print("Type /exit to quit. Tool results and errors are printed below.")
        conversation_id = uuid4().hex
        while True:
            try:
                prompt = input("You: ").strip()
            except EOFError:
                break
            if prompt.casefold() in {"/exit", "/quit"}:
                break
            if not prompt:
                continue
            try:
                task = await runtime.agent.start_task(
                    StartTask(conversation_id, prompt, model.id)
                )
                await _print_events(runtime, task.id)
            except Exception as error:
                _display_error(error, runtime.redactor)
    except (ContractError, OSError, ValueError) as error:
        _display_error(error, runtime.redactor if runtime else redactor)
    except Exception as error:
        _display_error(error, runtime.redactor if runtime else redactor)
    finally:
        if runtime is not None:
            try:
                await runtime.close()
            except Exception as error:
                _display_error(error, runtime.redactor)


def main() -> None:
    """Start the interactive client without exposing uncaught tracebacks.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    try:
        asyncio.run(_chat(_parser().parse_args()))
    except KeyboardInterrupt:
        print("\nChat interrupted.")
    except Exception as error:
        _display_error(error, Redactor())


if __name__ == "__main__":
    main()
