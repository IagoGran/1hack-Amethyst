"""Credential-free contract coverage for integration adapters."""

import asyncio
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from amethyst.adapters.fakes import InMemoryRepository, MemoryCredentialStore
from amethyst.adapters.models import (
    DeepSeekModelProvider,
    GeminiModelProvider,
    OllamaModelProvider,
    OpenAIModelProvider,
)
from amethyst.adapters.persistence import (
    SQLiteConnectionRepository,
    SQLiteConversationRepository,
    SQLiteSkillRepository,
)
from amethyst.adapters.tools import (
    BraveSearchTool,
    ChromaTool,
    MilvusTool,
    PostgreSQLReadOnlyTool,
    QdrantTool,
    SQLiteReadOnlyTool,
)
from amethyst.application.connections import ConnectionService
from amethyst.configuration.connections import (
    create_model_provider,
    secret_free_config,
    validate_connection,
)
from amethyst.domain.contracts import (
    Connection,
    ContractError,
    Conversation,
    ErrorCode,
    Message,
    ModelCompleted,
    ModelRequest,
    OperationContext,
    Skill,
    TextDelta,
    ToolCall,
    Usage,
)

CONTEXT = OperationContext(
    "task", "session", timeout_seconds=3, output_limit_bytes=4_096
)


def test_sqlite_repositories_survive_reopen_and_keep_snapshots(tmp_path) -> None:
    async def scenario() -> None:
        database = tmp_path / "amethyst.db"
        conversations = SQLiteConversationRepository(database)
        await conversations.save(
            Conversation("c", "Chat", (Message("assistant", "answer"),))
        )
        await SQLiteSkillRepository(database).save(
            Skill("s", "Skill", "Instructions", False)
        )
        await SQLiteConnectionRepository(database).save(
            Connection("x", "ollama", {"endpoint": "http://localhost:11434"})
        )

        reopened = SQLiteConversationRepository(database)
        assert await reopened.load("c") == Conversation(
            "c", "Chat", (Message("assistant", "answer"),)
        )
        assert (await SQLiteSkillRepository(database).load("s")).enabled is False
        assert (await SQLiteConnectionRepository(database).load("x")).options == {
            "endpoint": "http://localhost:11434"
        }
        assert [item.id for item in await reopened.list()] == ["c"]
        await reopened.delete("c")
        await reopened.delete("c")
        with pytest.raises(ContractError) as missing:
            await reopened.load("c")
        assert missing.value.code == ErrorCode.NOT_FOUND

    asyncio.run(scenario())


def test_sqlite_adapter_is_read_only_and_bounded(tmp_path) -> None:
    async def scenario() -> None:
        path = tmp_path / "source.db"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE records (id INTEGER, value TEXT)")
            connection.executemany(
                "INSERT INTO records VALUES (?, ?)", [(1, "one"), (2, "two")]
            )
        tool = SQLiteReadOnlyTool(path, "source-db")
        result = await tool.execute(
            ToolCall("read", tool.definition.name, {"query": "SELECT * FROM records"}),
            CONTEXT,
        )
        payload = json.loads(result.content)
        assert [row["id"] for row in payload["rows"]] == [1, 2]
        assert result.sources[0].identifier == "source-db"

        for query in ("INSERT INTO records VALUES (3, 'three')", "PRAGMA user_version"):
            with pytest.raises(ContractError) as denied:
                await tool.execute(
                    ToolCall("write", tool.definition.name, {"query": query}), CONTEXT
                )
            assert denied.value.code == ErrorCode.PERMISSION_DENIED

        small = await tool.execute(
            ToolCall("small", tool.definition.name, {"query": "SELECT * FROM records"}),
            OperationContext("task", "session", output_limit_bytes=64),
        )
        assert len(small.content.encode()) <= 64
        assert small.truncated

    asyncio.run(scenario())


def test_openai_and_deepseek_stream_and_decode_tool_calls(monkeypatch) -> None:
    async def fake_stream(*args, **kwargs):
        yield {"choices": [{"delta": {"content": "hello"}, "finish_reason": None}]}
        yield {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {"name": "search", "arguments": '{"q":'},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        }
        yield {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"arguments": '"x"}'}}]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }

    monkeypatch.setattr("amethyst.adapters.models.providers.stream_json", fake_stream)

    async def scenario() -> None:
        request = ModelRequest("fixture-model", (Message("user", "Hi"),))
        for provider in (
            OpenAIModelProvider("secret"),
            DeepSeekModelProvider("secret"),
        ):
            events = [event async for event in provider.stream(request, CONTEXT)]
            assert events[0] == TextDelta("hello")
            assert events[-1] == ModelCompleted(
                Usage(2, 3), (ToolCall("call-1", "search", {"q": "x"}),), "tool_calls"
            )

    asyncio.run(scenario())


def test_gemini_streams_text_and_usage(monkeypatch) -> None:
    async def fake_stream(*args, **kwargs):
        yield {
            "candidates": [{"content": {"parts": [{"text": "Hi"}]}}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
        }

    monkeypatch.setattr("amethyst.adapters.models.providers.stream_json", fake_stream)

    async def scenario() -> None:
        provider = GeminiModelProvider("secret")
        events = [
            event
            async for event in provider.stream(
                ModelRequest("fixture-model", (Message("user", "Hello"),)), CONTEXT
            )
        ]
        assert events == [TextDelta("Hi"), ModelCompleted(Usage(4, 1))]

    asyncio.run(scenario())


def test_ollama_streams_ndjson_tool_call(monkeypatch) -> None:
    async def fake_stream(*args, **kwargs):
        yield {
            "message": {
                "tool_calls": [{"function": {"name": "lookup", "arguments": {"id": 7}}}]
            },
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 2,
        }

    monkeypatch.setattr("amethyst.adapters.models.providers.stream_json", fake_stream)

    async def scenario() -> None:
        provider = OllamaModelProvider()
        events = [
            event
            async for event in provider.stream(
                ModelRequest("local-model", (Message("user", "Hello"),)), CONTEXT
            )
        ]
        assert events[-1] == ModelCompleted(
            Usage(5, 2), (ToolCall("Ollama-0", "lookup", {"id": 7}),), "tool_calls"
        )

    asyncio.run(scenario())


def test_brave_search_bounds_results_and_preserves_sources(monkeypatch) -> None:
    tool = BraveSearchTool("fixture-secret", max_results=1)
    monkeypatch.setattr(
        tool,
        "_request",
        lambda query, count, timeout: {
            "web": {
                "results": [
                    {
                        "title": "One",
                        "description": "First",
                        "url": "https://example.test/1",
                    },
                    {
                        "title": "Two",
                        "description": "Second",
                        "url": "https://example.test/2",
                    },
                ]
            }
        },
    )

    async def scenario() -> None:
        result = await tool.execute(
            ToolCall("search", tool.definition.name, {"query": "fixture", "count": 8}),
            CONTEXT,
        )
        assert len(json.loads(result.content)) == 1
        assert result.sources[0].url == "https://example.test/1"
        assert result.truncated

    asyncio.run(scenario())


def test_vector_adapters_preserve_source_and_limit_output() -> None:
    class QdrantClient:
        def query_points(self, **kwargs):
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        id="q1", payload={"text": "match", "url": "https://source.test"}
                    )
                ]
            )

        def get_collection(self, collection):
            return object()

    class ChromaCollection:
        def query(self, **kwargs):
            return {
                "ids": [["c1"]],
                "documents": [["match"]],
                "metadatas": [[{"title": "Source"}]],
            }

        def count(self):
            return 1

    class ChromaClient:
        def get_collection(self, name):
            return ChromaCollection()

    class MilvusClient:
        def search(self, **kwargs):
            return [
                [
                    {
                        "id": "m1",
                        "entity": {"text": "match", "url": "https://source.test"},
                    }
                ]
            ]

        def describe_collection(self, name):
            return object()

    async def scenario() -> None:
        for tool in (
            QdrantTool("collection", QdrantClient()),
            ChromaTool("collection", ChromaClient()),
            MilvusTool("collection", MilvusClient()),
        ):
            result = await tool.execute(
                ToolCall(
                    "vector", tool.definition.name, {"vector": [0.1, 0.2], "limit": 99}
                ),
                CONTEXT,
            )
            assert json.loads(result.content)[0]["text"] == "match"
            assert result.sources[0].identifier

    asyncio.run(scenario())


def test_postgresql_adapter_fails_clearly_without_optional_driver(monkeypatch) -> None:
    async def scenario() -> None:
        tool = PostgreSQLReadOnlyTool("postgresql://fixture")

        def no_driver(*args, **kwargs):
            raise ImportError("optional driver is absent")

        monkeypatch.setattr(tool, "_query", no_driver)
        with pytest.raises(ContractError) as unavailable:
            await tool.execute(
                ToolCall("sql", tool.definition.name, {"query": "SELECT 1"}),
                CONTEXT,
            )
        assert unavailable.value.code == ErrorCode.UNAVAILABLE

    asyncio.run(scenario())


def test_postgresql_adapter_starts_a_read_only_transaction(monkeypatch) -> None:
    statements = []

    class Cursor:
        description = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement, params=None):
            statements.append(statement)
            if statement == "SELECT 1":
                self.description = (SimpleNamespace(name="value"),)

        def fetchmany(self, limit):
            return [(1,)]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return Cursor()

        def execute(self, statement, params=None):
            statements.append(statement)

    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *args, **kwargs: Connection()),
    )
    tool = PostgreSQLReadOnlyTool("postgresql://fixture")
    rows, columns, truncated = tool._query("SELECT 1", 1_024, 3)
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert statements[-1] == "SELECT 1"
    assert rows == [{"value": 1}]
    assert columns == ["value"]
    assert not truncated


def test_connection_validation_keeps_secrets_out_of_configuration() -> None:
    connection = Connection(
        "openai",
        "openai",
        {"model_id": "fixture-model", "endpoint": "https://api.example.test/v1"},
        credential_ref="openai-key",
    )
    assert validate_connection(connection) == connection
    assert "credential_ref" not in secret_free_config(connection)
    with pytest.raises(ContractError) as rejected:
        validate_connection(
            Connection("bad", "openai", {"nested": {"api_key": "leak"}})
        )
    assert rejected.value.code == ErrorCode.INVALID_INPUT

    async def scenario() -> None:
        credentials = MemoryCredentialStore()
        await credentials.set("openai-key", "fixture-secret")
        provider = await create_model_provider(connection, credentials)
        assert isinstance(provider, OpenAIModelProvider)
        missing = Connection(
            "missing",
            "openai",
            {"model_id": "fixture-model"},
            credential_ref="absent",
        )
        with pytest.raises(ContractError) as unavailable:
            await create_model_provider(missing, credentials)
        assert unavailable.value.code == ErrorCode.AUTHENTICATION

    asyncio.run(scenario())


def test_connection_service_crud_and_disabled_health() -> None:
    async def scenario() -> None:
        repository = InMemoryRepository[Connection]()
        service = ConnectionService(repository, MemoryCredentialStore())
        connection = Connection(
            "local-model",
            "ollama",
            {"model_id": "fixture-model"},
            enabled=False,
        )
        assert await service.add(connection) == connection
        assert await service.list() == (connection,)
        health = await service.test("local-model", CONTEXT)
        assert not health.available
        assert health.error_code == ErrorCode.PERMISSION_DENIED
        enabled = await service.set_enabled("local-model", True)
        assert enabled.enabled
        await service.delete("local-model")
        assert await service.list() == ()

    asyncio.run(scenario())
