import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import pytest

from amethyst.application.service import AgentService, ProviderBinding, ToolBinding
from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
    ApprovalRequest,
    ContractError,
    Conversation,
    ErrorCode,
    ModelCapabilities,
    ModelCompleted,
    ModelEvent,
    ModelRequest,
    OperationContext,
    Skill,
    StartTask,
    TaskEvent,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.ports.application import ApplicationService
from amethyst.security.credentials import Redactor
from amethyst.security.permissions import ApprovalEngine, PermissionService
from amethyst.security.retention import DiagnosticStore, TaskTemporaryData
from amethyst.security.workspace import Workspace
from tests.support.fakes import InMemoryRepository

REQUEST = StartTask(
    "conversation", "Please inspect and fix the supplied error.", "model"
)


class Model:
    def __init__(
        self, responses: list[tuple[ModelEvent, ...] | ContractError] | None = None
    ) -> None:
        """Initialize model state and dependencies.

        Parameters
        ----------
        responses : list[tuple[ModelEvent, ...] | ContractError] | None
            Deterministic model events or failures emitted by the fixture.

        Returns
        -------
        None
        """
        self.responses = responses or [
            (TextDelta("Done."), ModelCompleted(Usage(10, 2)))
        ]
        self.requests: list[ModelRequest] = []
        self.block = False
        self.context_tokens = 40_000

    async def capabilities(self, model_id: str) -> ModelCapabilities:
        """Report the configured model capabilities and context capacity.

        Parameters
        ----------
        model_id : str
            Configured model identifier.

        Returns
        -------
        ModelCapabilities
            Supported generation features and context capacity.
        """
        return ModelCapabilities(True, True, self.context_tokens)

    async def stream(
        self, request: ModelRequest, context: OperationContext
    ) -> AsyncIterator[ModelEvent]:
        """Provide the stream test fixture.

        Parameters
        ----------
        request : ModelRequest
            Typed request describing the operation and its scope.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Yields
        ------
        ModelEvent
            Ordered values produced by the operation.
        """
        self.requests.append(request)
        if self.block:
            await asyncio.sleep(20)
        response = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        if isinstance(response, ContractError):
            raise response
        for event in response:
            await asyncio.sleep(0)
            yield event


class Tool:
    def __init__(
        self,
        *,
        readonly: bool = True,
        fail: ContractError | None = None,
        content: str = "Result",
    ) -> None:
        """Initialize tool state and dependencies.

        Parameters
        ----------
        readonly : bool
            Whether the test tool advertises read-only execution.
        fail : ContractError | None
            Optional deterministic failure injected by the test.
        content : str
            Text content to display, persist, or return.

        Returns
        -------
        None
        """
        self.readonly = readonly
        self.calls = 0
        self.fail = fail
        self.content = content
        self.wrong_id = False

    @property
    def definition(self) -> ToolDefinition:
        """Describe the tool name and its accepted arguments.

        Parameters
        ----------
        None

        Returns
        -------
        ToolDefinition
            Model-visible tool schema.
        """
        return ToolDefinition("fixture.read", "Read fixture", read_only=self.readonly)

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Provide the execute test fixture.

        Parameters
        ----------
        call : ToolCall
            Tool invocation with its identifier, name, and arguments.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        ToolResult
            Bounded result with call identity and source metadata.
        """
        self.calls += 1
        if self.fail and self.calls == 1:
            raise self.fail
        return ToolResult("wrong" if self.wrong_id else call.id, self.content)


def make_app(
    root: Path,
    model: Model | None = None,
    tools: tuple[ToolBinding, ...] = (),
    limits: Limits | None = None,
) -> AgentService:
    """Provide the make app test fixture.

    Parameters
    ----------
    root : Path
        Application-owned data directory or approved workspace root.
    model : Model | None
        Model provider or deterministic provider fixture.
    tools : tuple[ToolBinding, ...]
        Enabled tool bindings supplied to the agent.
    limits : Limits | None
        Validated operational resource limits.

    Returns
    -------
    AgentService
        Value produced by the operation.
    """
    engine = ApprovalEngine("session")
    permissions = PermissionService("session")
    redactor = Redactor()
    return AgentService(
        session_id="session",
        providers={"model": ProviderBinding(model or Model(), "fixture")},
        conversations=InMemoryRepository[Conversation](),
        approvals=engine,
        permissions=permissions,
        tools=tools,
        limits=limits,
        workspace=Workspace(root, permissions, engine),
        redactor=redactor,
        temporary=TaskTemporaryData(root),
        diagnostics=DiagnosticStore(root / "logs", redactor),
    )


async def collect(
    app: ApplicationService,
    task_id: str,
    *,
    approve: ApprovalEngine | None = None,
    grant: bool = True,
) -> list[TaskEvent]:
    """Provide the collect test fixture.

    Parameters
    ----------
    app : ApplicationService
        Application or Qt instance used by the operation.
    task_id : str
        Identifier of the task being inspected or controlled.
    approve : ApprovalEngine | None
        Approval service used to decide the test proposal.
    grant : bool
        Read grant used to authorize the operation.

    Returns
    -------
    list[TaskEvent]
        Value produced by the operation.
    """
    events = []
    async with asyncio.timeout(5):
        async for event in app.events(task_id):
            events.append(event)
            if isinstance(event.payload, ApprovalRequest) and approve:
                await approve.decide(event.payload.id, granted=grant)
    return events


def response(call: ToolCall) -> tuple[ModelEvent, ...]:
    """Provide the response test fixture.

    Parameters
    ----------
    call : ToolCall
        Tool invocation with its identifier, name, and arguments.

    Returns
    -------
    tuple[ModelEvent, ...]
        Value produced by the operation.
    """
    return TextDelta(
        "Plan: inspect the relevant result before deciding the next action.\n"
    ), ModelCompleted(Usage(10, 20), (call,), "tool_calls")


def test_agent_plan_tool_validation_and_conversation_resume(tmp_path: Path) -> None:
    """Verify agent plan tool validation and conversation resume.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise agent plan tool validation and conversation resume.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        tool = Tool()
        model = Model(
            [
                response(ToolCall("call", "fixture.read")),
                (TextDelta("Validated."), ModelCompleted(Usage(20, 3))),
            ]
        )
        app = make_app(tmp_path, model, (ToolBinding(tool, "data"),))
        app.permissions.grant("fixture.read", "data")
        task = await app.start_task(REQUEST)
        events = await collect(app, task.id)
        assert (await app.get_task(task.id)).status == TaskStatus.COMPLETED
        assert tool.calls == 1
        assert any(isinstance(e.payload, ToolResult) for e in events)
        assert [e.sequence for e in events] == list(range(1, len(events) + 1))
        assert [e async for e in app.events(task.id, len(events))] == []
        saved = await app.conversations.load("conversation")
        assert [m.role for m in saved.messages] == [
            "user",
            "assistant",
            "tool",
            "assistant",
        ]
        assert model.requests[1].messages[-1].tool_call_id == "call"
        assert not list(tmp_path.glob("amethyst-task-*"))
        resumed = await app.start_task(replace(REQUEST, request="Continue"))
        await collect(app, resumed.id)
        assert any(m.content == "Validated." for m in model.requests[-1].messages)
        await app.close()
        assert not app.permissions.inspect()
        with pytest.raises(ContractError):
            await app.start_task(REQUEST)

    asyncio.run(scenario())


@pytest.mark.parametrize("grant", [True, False])
def test_protected_tool_requires_explicit_approval(tmp_path: Path, grant: bool) -> None:
    """Verify protected tool requires explicit approval.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.
    grant : bool
        Read grant used to authorize the operation.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise protected tool requires explicit approval.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        tool = Tool(readonly=False)
        model = Model(
            [
                response(ToolCall("call", "fixture.read")),
                (TextDelta("Completed."), ModelCompleted(Usage(2, 2))),
            ]
        )
        app = make_app(tmp_path, model, (ToolBinding(tool, "resource"),))
        task = await app.start_task(REQUEST)
        events = await collect(app, task.id, approve=app.approvals, grant=grant)
        assert tool.calls == int(grant)
        assert (await app.get_task(task.id)).status == (
            TaskStatus.COMPLETED if grant else TaskStatus.FAILED
        )
        proposals = [
            e.payload for e in events if isinstance(e.payload, ApprovalRequest)
        ]
        assert proposals[0].actions[0].high_impact
        assert any(
            isinstance(e.payload, TaskStateChanged)
            and e.payload.status == TaskStatus.AWAITING_APPROVAL
            for e in events
        )
        assert all(a.status.value == "expired" for a in app.approvals.inspect_all())

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["before_start", "model", "approval"])
def test_cancellation_blocks_dispatch_and_closes_events(
    tmp_path: Path, mode: str
) -> None:
    """Verify cancellation blocks dispatch and closes events.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.
    mode : str
        File permissions or fixture execution mode.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise cancellation blocks dispatch and closes events.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        tool = Tool()
        model = Model([response(ToolCall("call", "fixture.read"))])
        model.block = mode == "model"
        app = make_app(tmp_path, model, (ToolBinding(tool, "data"),))
        task = await app.start_task(REQUEST)
        assert (await app.start_task(REQUEST)).id == task.id
        with pytest.raises(ContractError):
            await app.start_task(replace(REQUEST, request="different"))
        if mode == "model":
            while not model.requests:
                await asyncio.sleep(0)
        if mode == "approval":
            async for event in app.events(task.id):
                if isinstance(event.payload, ApprovalRequest):
                    break
        assert (await app.cancel_task(task.id)).status == TaskStatus.CANCELLED
        assert (await app.cancel_task(task.id)).status == TaskStatus.CANCELLED
        await collect(app, task.id)
        assert tool.calls == 0
        assert not list(tmp_path.glob("amethyst-task-*"))

    asyncio.run(scenario())


def test_budget_pause_requires_explicit_increase(tmp_path: Path) -> None:
    """Verify budget pause requires explicit increase.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise budget pause requires explicit increase.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        model = Model()
        app = make_app(tmp_path, model, limits=Limits(task_tokens=1))
        task = await app.start_task(REQUEST)
        async for event in app.events(task.id):
            if (
                isinstance(event.payload, TaskStateChanged)
                and event.payload.status == TaskStatus.PAUSED_FOR_BUDGET
            ):
                assert not model.requests
                with pytest.raises(ContractError):
                    await app.increase_budget(task.id, 0)
                await app.increase_budget(task.id, 100_000)
                break
        await collect(app, task.id)
        assert (await app.get_task(task.id)).status == TaskStatus.COMPLETED
        with pytest.raises(ContractError):
            await app.increase_budget(task.id, 100)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "idle",
        "total",
        "task",
        "capacity",
        "input",
        "output",
        "usage",
        "missing_completion",
        "after_completion",
    ],
)
def test_model_limits_produce_terminal_failure(tmp_path: Path, mode: str) -> None:
    """Verify model limits produce terminal failure.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.
    mode : str
        File permissions or fixture execution mode.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise model limits produce terminal failure.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        model = Model()
        limits = Limits(retries=0)
        if mode in {"idle", "total", "task"}:
            model.block = True
            if mode == "idle":
                limits = replace(limits, model_idle_seconds=0.01)
            elif mode == "total":
                limits = replace(limits, model_total_seconds=0.01)
            else:
                limits = replace(limits, task_seconds=0.01)
        if mode == "capacity":
            model.context_tokens = 1
        if mode == "input":
            limits = replace(limits, input_tokens=1)
        if mode == "output":
            model.responses = [(TextDelta("too much"), ModelCompleted(Usage(1, 1)))]
            limits = replace(limits, output_tokens=2)
        if mode == "usage":
            model.responses = [(ModelCompleted(Usage(999999, 1)),)]
        if mode == "missing_completion":
            model.responses = [(TextDelta("partial"),)]
        if mode == "after_completion":
            model.responses = [(ModelCompleted(Usage(1, 1)), TextDelta("extra"))]
        app = make_app(tmp_path, model, limits=limits)
        task = await app.start_task(REQUEST)
        events = await collect(app, task.id)
        assert (await app.get_task(task.id)).status == TaskStatus.FAILED
        assert any(isinstance(e.payload, TaskFailure) for e in events)
        assert len(model.requests) <= 1

    asyncio.run(scenario())


def test_retry_usage_and_safe_tool_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify retry usage and safe tool retries.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.
    monkeypatch : pytest.MonkeyPatch
        Pytest fixture for temporary dependency replacements.

    Returns
    -------
    None
    """
    for module in ("model_execution", "tool_dispatch"):
        monkeypatch.setattr(
            f"amethyst.application.{module}.retry_delay",
            lambda error, attempt, retries, safe: (
                0.0 if safe and error.transient and attempt < retries else None
            ),
        )

    async def scenario() -> None:
        """Exercise retry usage and safe tool retries.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        transient = ContractError(
            ErrorCode.UNAVAILABLE, "Temporary", transient=True, usage=Usage(4, 1)
        )
        tool = Tool(fail=transient)
        model = Model(
            [
                transient,
                response(ToolCall("call", "fixture.read")),
                (TextDelta("Recovered."), ModelCompleted(Usage(2, 2))),
            ]
        )
        app = make_app(tmp_path, model, (ToolBinding(tool, "data"),))
        app.permissions.grant("fixture.read", "data")
        task = await app.start_task(REQUEST)
        events = await collect(app, task.id)
        assert (await app.get_task(task.id)).status == TaskStatus.COMPLETED
        assert tool.calls == 2
        assert Usage(4, 1) in [e.payload for e in events]
        assert len(model.requests) == 3

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode",
    [
        "mutating_failure",
        "wrong_id",
        "sql_write",
        "disabled",
        "missing_plan",
        "duplicate_calls",
    ],
)
def test_unsafe_and_invalid_tool_work_stops(tmp_path: Path, mode: str) -> None:
    """Verify unsafe and invalid tool work stops.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.
    mode : str
        File permissions or fixture execution mode.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise unsafe and invalid tool work stops.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        tool = Tool(
            readonly=mode != "mutating_failure",
            fail=ContractError(ErrorCode.OUTCOME_UNKNOWN, "Unknown", transient=True)
            if mode == "mutating_failure"
            else None,
        )
        tool.wrong_id = mode == "wrong_id"
        call = ToolCall(
            "call",
            "fixture.read",
            {"query": "DELETE FROM data"} if mode == "sql_write" else {},
        )
        first = response(call)
        if mode == "missing_plan":
            first = (ModelCompleted(Usage(1, 1), (call,), "tool_calls"),)
        if mode == "duplicate_calls":
            first = (
                TextDelta("Plan"),
                ModelCompleted(Usage(1, 1), (call, call), "tool_calls"),
            )
        app = make_app(
            tmp_path,
            Model([first]),
            (
                ToolBinding(
                    tool,
                    "data",
                    kind="sql" if mode == "sql_write" else "text",
                    enabled=mode != "disabled",
                ),
            ),
        )
        task = await app.start_task(REQUEST)
        await collect(app, task.id, approve=app.approvals)
        assert (await app.get_task(task.id)).status == TaskStatus.FAILED
        assert tool.calls <= 1

    asyncio.run(scenario())


def test_workspace_plan_approval_apply_and_recheck(tmp_path: Path) -> None:
    """Verify workspace plan approval apply and recheck.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise workspace plan approval apply and recheck.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        (tmp_path / "file").write_text("old\n")
        model = Model(
            [
                response(ToolCall("read", "workspace.read", {"path": "file"})),
                response(
                    ToolCall(
                        "edit", "workspace.edit", {"path": "file", "content": "new\n"}
                    )
                ),
                (TextDelta("Change validated."), ModelCompleted(Usage(3, 2))),
            ]
        )
        app = make_app(tmp_path, model)
        app.permissions.grant("workspace.read", str(tmp_path), recursive=True)
        task = await app.start_task(REQUEST)
        await collect(app, task.id, approve=app.approvals)
        assert (await app.get_task(task.id)).status == TaskStatus.COMPLETED
        assert (tmp_path / "file").read_text() == "new\n"
        assert app.approvals.inspect_all()[0].request.actions[0].changes == ()

    asyncio.run(scenario())


def test_skills_and_redaction_are_applied_before_persistence(tmp_path: Path) -> None:
    """Verify skills and redaction are applied before persistence.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise skills and redaction are applied before persistence.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        model = Model(
            [
                (
                    TextDelta("secret-"),
                    TextDelta("value\nSafe.\n"),
                    ModelCompleted(Usage(1, 5)),
                )
            ]
        )
        app = make_app(tmp_path, model)
        app.redactor.register("secret-value")
        skills = InMemoryRepository[Skill]()
        await skills.save(
            Skill(
                "s", "Debug", "Trace the supplied failure.", condition="contains:error"
            )
        )
        app.skills = skills
        task = await app.start_task(REQUEST)
        events = await collect(app, task.id)
        assert "Trace the supplied failure." in model.requests[0].messages[0].content
        assert "secret-value" not in "".join(
            e.payload.text for e in events if isinstance(e.payload, TextDelta)
        )
        assert "secret-value" not in repr(await app.conversations.load("conversation"))
        with pytest.raises(ContractError):
            await app.get_task("missing")
        with pytest.raises(ContractError):
            await app.start_task(replace(REQUEST, model_connection_id="missing"))
        with pytest.raises(ContractError):
            await app.start_task(replace(REQUEST, request=" "))
        with pytest.raises(ContractError):
            await anext(app.events(task.id, -1))

    asyncio.run(scenario())
