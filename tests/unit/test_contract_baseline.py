"""Deterministic S0 checks, not the MVP acceptance suite."""

import asyncio
from pathlib import Path

import pytest

from amethyst.domain.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    Connection,
    ContractError,
    Conversation,
    ErrorCode,
    Message,
    ModelCompleted,
    ModelRequest,
    OperationContext,
    ProposedAction,
    SandboxRequest,
    Skill,
    StartTask,
    TaskStateChanged,
    TextDelta,
    ToolCall,
    Usage,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.ports.application import ApplicationService
from amethyst.ports.approval import ApprovalService
from amethyst.ports.credentials import CredentialStore
from amethyst.ports.model_provider import ModelProvider
from amethyst.ports.persistence import (
    ConnectionRepository,
    ConversationRepository,
    SkillRepository,
)
from amethyst.ports.sandbox import Sandbox
from amethyst.ports.tool import AgentTool, ConnectionTester
from tests.support.deny_all import DenyAllApprovalService
from tests.support.disabled_sandbox import DisabledSandbox
from tests.support.fakes import (
    FakeApplicationService,
    FakeModelProvider,
    FakeTool,
    InMemoryRepository,
    MemoryCredentialStore,
)

CONTEXT = OperationContext("task", "session")
ACTION = ProposedAction(
    "action", "workspace.edit", "Edit file", ("workspace",), "digest"
)


def test_model_stream_and_tool_limits() -> None:
    """Verify model stream and tool limits.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise model stream and tool limits.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        model: ModelProvider = FakeModelProvider(("One", " two"))
        request = ModelRequest("fixture", (Message("user", "Hello"),))
        events = [event async for event in model.stream(request, CONTEXT)]
        assert events[:-1] == [TextDelta("One"), TextDelta(" two")]
        assert events[-1] == ModelCompleted(Usage(4, 2))
        assert (await model.capabilities("fixture")).streaming

        tool: AgentTool = FakeTool("éé")
        result = await tool.execute(
            ToolCall("call", "fake.read"),
            OperationContext("task", "session", output_limit_bytes=3),
        )
        assert result.call_id == "call"
        assert result.content == "é"
        assert result.truncated
        with pytest.raises(ContractError) as error:
            await tool.execute(ToolCall("call", "unknown"), CONTEXT)
        assert error.value.code == ErrorCode.INVALID_INPUT
        tester: ConnectionTester = FakeTool()
        assert (await tester.test_connection(CONTEXT)).available

    asyncio.run(scenario())


def test_task_events_replay_and_isolation() -> None:
    """Verify task events replay and isolation.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise task events replay and isolation.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        app: ApplicationService = FakeApplicationService(("One", " two"))
        first = await app.start_task(StartTask("conversation", "Hello", "fixture"))
        second = await app.start_task(StartTask("other", "World", "fixture"))
        events = [event async for event in app.events(first.id)]
        assert [event.sequence for event in events] == list(range(1, 6))
        assert all(event.task_id == first.id for event in events)
        assert [
            event.payload.status
            for event in events
            if isinstance(event.payload, TaskStateChanged)
        ] == [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED]
        assert [event async for event in app.events(first.id, 2)] == events[2:]
        assert [event async for event in app.events(first.id, 5)] == []
        assert (await app.get_task(first.id)).conversation_id == "conversation"
        # Completion does not depend on having a subscriber.
        assert (await app.get_task(second.id)).status == TaskStatus.COMPLETED
        assert (await app.cancel_task(first.id)).status == TaskStatus.COMPLETED

    asyncio.run(scenario())


@pytest.mark.parametrize("start_worker", [False, True])
def test_cancellation_is_terminal(start_worker: bool) -> None:
    """Verify cancellation is terminal.

    Parameters
    ----------
    start_worker : bool
        Whether the fixture starts its asynchronous worker.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise cancellation is terminal.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        app: ApplicationService = FakeApplicationService(("never finish",) * 10)
        task = await app.start_task(StartTask("conversation", "Hello", "fixture"))
        if start_worker:
            await asyncio.sleep(0)
        assert (await app.cancel_task(task.id)).status == TaskStatus.CANCELLED
        before = [event async for event in app.events(task.id)]
        await asyncio.sleep(0)
        await app.cancel_task(task.id)
        assert [event async for event in app.events(task.id)] == before
        assert before[-1].payload == TaskStateChanged(TaskStatus.CANCELLED)
        assert not any(isinstance(event.payload, TextDelta) for event in before)

    asyncio.run(scenario())


def test_missing_task_and_invalid_budget_fail_clearly() -> None:
    """Verify missing task and invalid budget fail clearly.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise missing task and invalid budget fail clearly.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        app: ApplicationService = FakeApplicationService()
        with pytest.raises(ContractError) as missing:
            await app.get_task("missing")
        assert missing.value.code == ErrorCode.NOT_FOUND
        task = await app.start_task(StartTask("conversation", "Hello", "fixture"))
        with pytest.raises(ContractError) as invalid:
            await app.increase_budget(task.id, 0)
        assert invalid.value.code == ErrorCode.INVALID_INPUT
        with pytest.raises(ContractError) as unsupported:
            await app.increase_budget(task.id, 100)
        assert unsupported.value.code == ErrorCode.UNAVAILABLE
        await app.cancel_task(task.id)

    asyncio.run(scenario())


def test_repository_crud_and_detached_snapshots() -> None:
    """Verify repository crud and detached snapshots.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise repository crud and detached snapshots.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        conversations: ConversationRepository = InMemoryRepository[Conversation]()
        await conversations.save(Conversation("b", "Second"))
        await conversations.save(
            Conversation("a", "First", (Message("user", "Hello"),))
        )
        assert [value.id for value in await conversations.list()] == ["a", "b"]
        await conversations.save(Conversation("a", "Updated"))
        assert (await conversations.load("a")).title == "Updated"
        await conversations.delete("a")
        await conversations.delete("a")
        with pytest.raises(ContractError) as missing:
            await conversations.load("a")
        assert missing.value.code == ErrorCode.NOT_FOUND
        assert await InMemoryRepository[Conversation]().list() == ()

        skills: SkillRepository = InMemoryRepository[Skill]()
        await skills.save(Skill("s", "Review", "Review changes", enabled=False))
        assert not (await skills.load("s")).enabled
        connections: ConnectionRepository = InMemoryRepository[Connection]()
        original = Connection(
            "c", "fixture", {"model_id": "test"}, credential_ref="key"
        )
        await connections.save(original)
        original.options["model_id"] = "changed"
        loaded = await connections.load("c")
        assert loaded.options["model_id"] == "test"
        loaded.options.clear()
        assert (await connections.load("c")).options == {"model_id": "test"}

    asyncio.run(scenario())


def test_credentials_stay_in_instance_memory() -> None:
    """Verify credentials stay in instance memory.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise credentials stay in instance memory.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        memory = MemoryCredentialStore()
        credentials: CredentialStore = memory
        await credentials.set("reference", "fixture-secret")
        assert await credentials.get("reference") == "fixture-secret"
        assert await MemoryCredentialStore().get("reference") is None
        memory.clear()
        assert await credentials.get("reference") is None
        await credentials.delete("reference")

    asyncio.run(scenario())


def test_placeholder_approvals_always_deny_execution() -> None:
    """Verify placeholder approvals always deny execution.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise placeholder approvals always deny execution.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        approvals: ApprovalService = DenyAllApprovalService()
        proposal = ApprovalRequest("approval", "task", "session", (ACTION,))
        assert (await approvals.request(proposal)).status == ApprovalStatus.DENIED
        with pytest.raises(ContractError) as duplicate:
            await approvals.request(proposal)
        assert duplicate.value.code == ErrorCode.CONFLICT
        with pytest.raises(ContractError) as grant:
            await approvals.decide("approval", granted=True)
        assert grant.value.code == ErrorCode.PERMISSION_DENIED
        for fingerprint in ("digest", "changed"):
            with pytest.raises(ContractError) as execute:
                await approvals.consume("approval", "action", fingerprint, CONTEXT)
            assert execute.value.code == ErrorCode.PERMISSION_DENIED
        assert (await approvals.revoke("approval")).status == ApprovalStatus.REVOKED
        await approvals.expire_task("task")
        assert (await approvals.inspect("approval")).status == ApprovalStatus.EXPIRED
        await approvals.end_session("session")

    asyncio.run(scenario())


@pytest.mark.parametrize("actions", [(), (ACTION, ACTION)])
def test_approval_requires_explicit_distinct_actions(
    actions: tuple[ProposedAction, ...],
) -> None:
    """Verify approval requires explicit distinct actions.

    Parameters
    ----------
    actions : tuple[ProposedAction, ...]
        Actions explicitly included in the approval proposal.

    Returns
    -------
    None
    """
    with pytest.raises(ValueError):
        ApprovalRequest("approval", "task", "session", actions)


def test_disabled_sandbox_has_no_host_fallback(tmp_path: Path) -> None:
    """Verify disabled sandbox has no host fallback.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise disabled sandbox has no host fallback.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        marker = tmp_path / "must-not-exist"
        sandbox: Sandbox = DisabledSandbox()
        request = SandboxRequest(
            "action", "approval", "digest", tmp_path, ("touch", str(marker))
        )
        assert not request.network_enabled
        with pytest.raises(ContractError) as error:
            await sandbox.run(request, CONTEXT)
        assert error.value.code == ErrorCode.UNAVAILABLE
        assert not marker.exists()

    asyncio.run(scenario())
