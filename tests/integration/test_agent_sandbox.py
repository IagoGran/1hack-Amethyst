"""Credential-free handoff checks for desktop events and provider tool results."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from amethyst.application.service import AgentService, ProviderBinding
from amethyst.domain.contracts import (
    ApprovalRequest,
    Conversation,
    ModelCapabilities,
    ModelCompleted,
    ModelEvent,
    ModelRequest,
    OperationContext,
    StartTask,
    TaskEvent,
    TaskFailure,
    TextDelta,
    ToolCall,
    ToolResult,
    Usage,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.security.permissions import ApprovalEngine, PermissionService
from amethyst.security.sandbox import DockerSandbox, ProcessResult
from tests.support.fakes import InMemoryRepository


@dataclass
class CommandProvider:
    """Request one command, then consume its result through the provider contract."""

    requests: list[ModelRequest] = field(default_factory=list)

    async def capabilities(self, model_id: str) -> ModelCapabilities:
        """Advertise deterministic streaming and tool support.

        Parameters
        ----------
        model_id : str
            Fixture model identifier.

        Returns
        -------
        ModelCapabilities
            Limits used by the application.
        """
        return ModelCapabilities(True, True, 40_000)

    async def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Plan one tool call and then acknowledge the returned exit status.

        Parameters
        ----------
        request : ModelRequest
            Prompt and tool results.
        context : OperationContext
            Application-owned request limits.

        Yields
        ------
        ModelEvent
            Streaming text and terminal usage/tool calls.
        """
        self.requests.append(request)
        if len(self.requests) == 1:
            yield TextDelta(
                "Plan: run the approved tests and inspect their exit status."
            )
            yield ModelCompleted(
                Usage(10, 10),
                (ToolCall("command", "sandbox.run", {"argv": ["python", "-V"]}),),
                "tool_calls",
            )
        else:
            yield TextDelta("The command result has been inspected.")
            yield ModelCompleted(Usage(10, 10))


@dataclass
class Lifecycle:
    """Simulate the daemon while exercising real sandbox and approval logic."""

    uncertain: bool
    calls: list[tuple[str, ...]] = field(default_factory=list)

    async def run(
        self, args: tuple[str, ...], timeout: float, output_limit: int
    ) -> ProcessResult:
        """Return daemon metadata and a nonzero command result.

        Parameters
        ----------
        args : tuple[str, ...]
            Docker lifecycle arguments.
        timeout : float
            Remaining deadline.
        output_limit : int
            Combined output limit.

        Returns
        -------
        ProcessResult
            Recorded fixture response.
        """
        self.calls.append(args)
        if args[0] == "image":
            return ProcessResult(0, "null", "")
        if args[0] == "inspect":
            return ProcessResult(
                0,
                json.dumps(
                    {
                        "Status": "running" if self.uncertain else "exited",
                        "Running": self.uncertain,
                        "Error": "",
                        "ExitCode": 7,
                    }
                ),
                "",
            )
        return ProcessResult(0, "test output", "")


async def collect(app: AgentService, grant: bool) -> tuple[str, list[TaskEvent]]:
    """Drive the exact user approval boundary consumed by the desktop.

    Parameters
    ----------
    app : AgentService
        Composed application.
    grant : bool
        Simulated explicit user decision.

    Returns
    -------
    tuple[str, list[TaskEvent]]
        Task identifier and complete event stream.
    """
    task = await app.start_task(StartTask("conversation", "Run the tests", "fixture"))
    events = []
    async with asyncio.timeout(5):
        async for event in app.events(task.id):
            events.append(event)
            if isinstance(event.payload, ApprovalRequest):
                assert event.payload.actions[0].tool_name == "sandbox.run"
                await app.approvals.decide(event.payload.id, granted=grant)
    return task.id, events


@pytest.mark.parametrize(
    "grant,uncertain", [(True, False), (False, False), (True, True)]
)
def test_application_sandbox_handoff(
    tmp_path: Path, grant: bool, uncertain: bool
) -> None:
    """Keep approval decisions, provider results, cleanup, and task events aligned.

    Parameters
    ----------
    tmp_path : Path
        Disposable workspace.
    grant : bool
        Explicit user authorization.
    uncertain : bool
        Whether daemon state fails to confirm completion.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Compose application ports and verify the complete command handoff.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        approvals = ApprovalEngine("session")
        provider = CommandProvider()
        transport = Lifecycle(uncertain)
        sandbox = DockerSandbox(
            tmp_path, "fixture@sha256:" + "a" * 64, approvals, transport, enabled=True
        )
        app = AgentService(
            session_id="session",
            providers={"fixture": ProviderBinding(provider, "fixture")},
            conversations=InMemoryRepository[Conversation](),
            approvals=approvals,
            permissions=PermissionService("session"),
            sandbox=sandbox,
        )
        try:
            task_id, events = await collect(app, grant)
            completed = grant and not uncertain
            assert (await app.get_task(task_id)).status == (
                TaskStatus.COMPLETED if completed else TaskStatus.FAILED
            )
            results = [e.payload for e in events if isinstance(e.payload, ToolResult)]
            if completed:
                assert json.loads(results[0].content)["exit_code"] == 7
                assert len(provider.requests) == 2
                assert any(m.role == "tool" for m in provider.requests[-1].messages)
            else:
                assert not results
                assert any(isinstance(e.payload, TaskFailure) for e in events)
                assert len(provider.requests) == 1
            assert sum(args[0] == "create" for args in transport.calls) == int(grant)
            if grant:
                assert transport.calls[-1][0] == "rm"
            else:
                assert not transport.calls
        finally:
            await app.close()

    asyncio.run(scenario())
