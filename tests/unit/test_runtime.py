"""Composition checks for settings, connector aliases, and credential boundaries."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from amethyst.adapters.persistence import create_sqlite_repositories
from amethyst.adapters.tools.vector import ChromaTool, MilvusTool, QdrantTool
from amethyst.application.limits import bounded_result
from amethyst.application.runtime import DesktopRuntime, NamedTool
from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
    Connection,
    ContractError,
    ErrorCode,
    OperationContext,
    ToolCall,
)
from amethyst.ports.tool import AgentTool


def test_runtime_credentials_limits_and_disabled_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep secrets out of persistence and retain operational limits on restart.

    Parameters
    ----------
    tmp_path : Path
        Disposable application-data directory.
    monkeypatch : pytest.MonkeyPatch
        Force memory-only credential storage.

    Returns
    -------
    None
    """
    monkeypatch.setattr("amethyst.security.credentials.native_keyring", lambda: None)

    async def scenario() -> None:
        """Exercise a complete credential/settings lifecycle.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        database = tmp_path / "app.sqlite3"
        runtime = await DesktopRuntime.open(database)
        model = Connection("model", "openai", {"model_id": "fixture"})
        try:
            with pytest.raises(ContractError):
                await runtime.save_connection(model)
            await runtime.save_connection(model, "private-fixture-value")
            await runtime.configure("model")
            assert runtime.agent.providers["model"].model_id == "fixture"
            assert runtime.redactor.redact("private-fixture-value") == "[REDACTED]"
            assert b"private-fixture-value" not in database.read_bytes()
            runtime.set_limits(Limits(task_tokens=12345, tool_seconds=12.5))
            await runtime.connections.set_enabled("model", False)
            with pytest.raises(ContractError):
                await runtime.configure("model")
        finally:
            await runtime.close()
        restarted = await DesktopRuntime.open(database)
        try:
            assert restarted.agent.limits.task_tokens == 12345
            assert restarted.agent.limits.tool_seconds == 12.5
            assert await restarted.credentials.get("connection:model") is None
            await restarted.connections.set_enabled("model", True)
            with pytest.raises(ContractError) as missing:
                await restarted.configure("model")
            assert missing.value.code == ErrorCode.AUTHENTICATION
        finally:
            await restarted.close()

    asyncio.run(scenario())


def test_repository_operations_close_sqlite_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure initialization and CRUD release database handles deterministically.

    Parameters
    ----------
    tmp_path : Path
        Disposable database directory.
    monkeypatch : pytest.MonkeyPatch
        Track database handles opened by the production repository.

    Returns
    -------
    None
    """
    original_connect = sqlite3.connect
    handles: list[sqlite3.Connection] = []

    def connect(*args, **kwargs) -> sqlite3.Connection:
        """Track one real SQLite handle.

        Parameters
        ----------
        *args : tuple
            SQLite positional settings.
        **kwargs : dict
            SQLite keyword settings.

        Returns
        -------
        sqlite3.Connection
            Real database handle.
        """
        # Allow test-only inspection of closed handles from the assertion thread.
        kwargs["check_same_thread"] = False
        connection: sqlite3.Connection = original_connect(*args, **kwargs)
        handles.append(connection)
        return connection

    async def scenario() -> None:
        """Perform real repository CRUD before checking handle closure.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        repos = create_sqlite_repositories(tmp_path / "app.sqlite3")
        record = Connection("model", "ollama", {"model_id": "fixture"})
        await repos.connections.save(record)
        assert await repos.connections.load(record.id) == record
        assert await repos.connections.list() == (record,)
        await repos.connections.delete(record.id)

    monkeypatch.setattr("amethyst.adapters.persistence.sqlite3.connect", connect)
    asyncio.run(scenario())
    assert len(handles) == 7
    for connection in handles:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


@pytest.mark.parametrize("kind", ["qdrant", "milvus", "chroma"])
def test_vector_adapter_results_fit_agent_contract(kind: str) -> None:
    """Translate actual vector adapter results into bounded agent retrieval chunks.

    Parameters
    ----------
    kind : str
        Approved vector connector.

    Returns
    -------
    None
    """
    record = {"id": "source", "text": "retrieved text", "url": "https://fixture.test"}
    adapter: AgentTool
    if kind == "qdrant":
        adapter = QdrantTool(
            "collection",
            SimpleNamespace(
                query_points=lambda **kw: SimpleNamespace(
                    points=[SimpleNamespace(id="source", payload=record)]
                )
            ),
        )
    elif kind == "milvus":
        adapter = MilvusTool(
            "collection",
            SimpleNamespace(search=lambda **kw: [[{"id": "source", "entity": record}]]),
        )
    else:
        collection = SimpleNamespace(
            query=lambda **kw: {
                "ids": [["source"]],
                "documents": [["retrieved text"]],
                "metadatas": [[{"url": "https://fixture.test"}]],
            }
        )
        adapter = ChromaTool(
            "collection", SimpleNamespace(get_collection=lambda name: collection)
        )
    connection = Connection("one", kind, {"collection": "collection"})
    named = NamedTool(adapter, connection)
    other = NamedTool(adapter, replace(connection, id="two"))
    assert named.definition.name != other.definition.name
    call = ToolCall("call", named.definition.name, {"vector": [0.2]})
    context = OperationContext("task", "session")
    result = bounded_result(
        asyncio.run(named.execute(call, context)), Limits(), "retrieval"
    )
    assert json.loads(result.content)["chunks"][0]["content"] == "retrieved text"
    assert result.sources[0].identifier == "source"
    assert result.call_id == "call"


def test_optional_connector_failure_does_not_disable_chat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report an unavailable optional adapter while retaining the selected model.

    Parameters
    ----------
    tmp_path : Path
        Disposable data directory.
    monkeypatch : pytest.MonkeyPatch
        Configure deterministic credential and optional-client failures.

    Returns
    -------
    None
    """
    monkeypatch.setattr("amethyst.security.credentials.native_keyring", lambda: None)

    async def unavailable(*args):
        """Represent an absent optional vendor dependency.

        Parameters
        ----------
        *args : tuple
            Unused factory inputs.

        Returns
        -------
        None
            Always raises an availability error.
        """
        raise ContractError(ErrorCode.UNAVAILABLE, "Optional client is unavailable.")

    async def scenario() -> None:
        """Configure a model alongside an unavailable connector.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        runtime = await DesktopRuntime.open(tmp_path / "app.sqlite3")
        try:
            await runtime.save_connection(
                Connection("model", "ollama", {"model_id": "fixture"})
            )
            await runtime.save_connection(
                Connection("vector", "qdrant", {"collection": "fixture"})
            )
            monkeypatch.setattr("amethyst.application.runtime.create_tool", unavailable)
            await runtime.configure("model")
            assert "model" in runtime.agent.providers
            assert not runtime.agent.tools
            assert runtime.warnings == ["vector: Optional client is unavailable."]
        finally:
            await runtime.close()

    asyncio.run(scenario())
