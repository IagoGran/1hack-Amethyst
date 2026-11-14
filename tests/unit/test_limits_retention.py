import asyncio
import json
from pathlib import Path

import pytest

from amethyst.application.limits import (
    Deadline,
    TokenBudget,
    bounded_result,
    require_read_only_sql,
    retry_delay,
)
from amethyst.configuration.limits import Limits
from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    Source,
    ToolResult,
    Usage,
)
from amethyst.security.credentials import OSCredentialStore, Redactor, StreamRedactor
from amethyst.security.retention import DiagnosticStore, TaskTemporaryData


@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO t VALUES (1)",
        "SELECT 1; DELETE FROM t",
        "WITH t AS (DELETE FROM data RETURNING *) SELECT * FROM t",
        "SELECT * INTO stolen FROM t",
        "PRAGMA journal_mode=WAL",
        "SELECT $$;DELETE$$",
        "SELECT lo_export(1, '/tmp/file')",
        "SELECT 1; SELECT 2",
        "",
    ],
)
def test_sql_write_admission_denied(query: str) -> None:
    """Verify sql write admission denied.

    Parameters
    ----------
    query : str
        SQL statement to execute through read-only enforcement.

    Returns
    -------
    None
    """
    with pytest.raises(ContractError) as error:
        require_read_only_sql(query)
    assert error.value.code == ErrorCode.PERMISSION_DENIED


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM table_name",
        "SELECT 'delete', \"update\" FROM t;",
        "/* update */ WITH t AS (SELECT 1) SELECT * FROM t -- delete",
    ],
)
def test_sql_reads_admitted(query: str) -> None:
    """Verify sql reads admitted.

    Parameters
    ----------
    query : str
        SQL statement to execute through read-only enforcement.

    Returns
    -------
    None
    """
    require_read_only_sql(query)


def test_limits_and_retry_classification() -> None:
    """Verify limits and retry classification.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    for seconds in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            Limits(task_seconds=seconds)
    for retries in (-1, 3):
        with pytest.raises(ValueError):
            Limits(retries=retries)
    budget = TokenBudget(10)
    assert budget.can_reserve(10)
    assert budget.charge(None, 4) == Usage(4, 0)
    assert not budget.can_reserve(7)
    budget.increase(10)
    assert budget.charge(Usage(2, 3), 7) == Usage(2, 3)
    for value in (0, -1, True):
        with pytest.raises(ContractError):
            budget.increase(value)
    with pytest.raises(ContractError):
        budget.charge(Usage(-1, 0), 2)
    transient = ContractError(
        ErrorCode.UNAVAILABLE, "safe", transient=True, retry_after_seconds=3
    )
    assert retry_delay(transient, 0, 2, safe=True) == 3
    assert retry_delay(transient, 2, 2, safe=True) is None
    assert retry_delay(transient, 0, 2, safe=False) is None
    assert (
        retry_delay(
            ContractError(ErrorCode.AUTHENTICATION, "safe", transient=True),
            0,
            2,
            safe=True,
        )
        is None
    )


def test_structured_and_byte_result_limits() -> None:
    """Verify structured and byte result limits.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    limits = Limits(sql_rows=2, retrieval_chunks=1, chunk_tokens=3, output_bytes=100)
    sql = bounded_result(
        ToolResult("id", json.dumps({"rows": [[1], [2], [3]], "columns": ["x"]})),
        limits,
        "sql",
    )
    assert json.loads(sql.content)["rows"] == [[1], [2]]
    assert sql.truncated
    retrieval = bounded_result(
        ToolResult(
            "id", json.dumps({"chunks": [{"content": "ééé"}, {"content": "second"}]})
        ),
        limits,
        "retrieval",
    )
    assert json.loads(retrieval.content)["chunks"] == [{"content": "é"}]
    assert retrieval.truncated
    assert bounded_result(ToolResult("id", "é" * 100), limits).truncated
    for content in ("not json", "[]", '{"chunks":[1]}'):
        with pytest.raises(ContractError):
            bounded_result(ToolResult("id", content), limits, "retrieval")
    shrunk = bounded_result(
        ToolResult("id", json.dumps({"rows": ["x" * 1000]})), limits, "sql"
    )
    assert json.loads(shrunk.content)["rows"] == []
    with pytest.raises(ContractError):
        bounded_result(
            ToolResult("id", json.dumps({"rows": [], "columns": "x" * 200})),
            limits,
            "sql",
        )
    with pytest.raises(ContractError):
        bounded_result(ToolResult("id", "ok", (Source("x" * 200),)), limits)


def test_deadline_excludes_only_approval_waits() -> None:
    """Verify deadline excludes only approval waits.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise deadline excludes only approval waits.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        now = [0.0]
        deadline = Deadline(10, lambda: now[0])

        async def wait() -> int:
            """Exercise deadline excludes only approval waits.

            Parameters
            ----------
            None

            Returns
            -------
            int
                Computed count or amount.
            """
            now[0] = 50
            return 1

        assert await deadline.approval_wait(wait) == 1
        assert deadline.remaining() == 10
        now[0] = 61
        with pytest.raises(ContractError):
            deadline.remaining()
        with pytest.raises(ContractError) as error:
            await Deadline(1).run(lambda: asyncio.sleep(1), 0.001)
        assert error.value.code == ErrorCode.TIMEOUT

    asyncio.run(scenario())


class Keyring:
    def __init__(self) -> None:
        """Initialize keyring state and dependencies.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.values: dict[str, str] = {}
        self.fail = False

    def get_password(self, service: str, username: str) -> str | None:
        """Resolve a credential through the explicit OS backend.

        Parameters
        ----------
        service : str
            Application service used by the operation.
        username : str
            Opaque credential account identifier.

        Returns
        -------
        str | None
            Value produced by the operation.
        """
        if self.fail:
            raise RuntimeError("private error")
        return self.values.get(username)

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store a credential through the explicit OS backend.

        Parameters
        ----------
        service : str
            Application service used by the operation.
        username : str
            Opaque credential account identifier.
        password : str
            Secret credential value kept outside ordinary settings.

        Returns
        -------
        None
        """
        if self.fail:
            raise RuntimeError("private error")
        self.values[username] = password

    def delete_password(self, service: str, username: str) -> None:
        """Remove a credential through the explicit OS backend.

        Parameters
        ----------
        service : str
            Application service used by the operation.
        username : str
            Opaque credential account identifier.

        Returns
        -------
        None
        """
        if self.fail:
            raise RuntimeError("private error")
        del self.values[username]


def test_os_credentials_and_memory_fallback() -> None:
    """Verify os credentials and memory fallback.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise os credentials and memory fallback.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        redactor = Redactor()
        backend = Keyring()
        store = OSCredentialStore(redactor, backend)
        await store.set("key", "top-secret")
        assert backend.values["key"] == "top-secret"
        assert await store.get("key") == "top-secret"
        reopened = OSCredentialStore(redactor, backend)
        assert await reopened.get("key") == "top-secret"
        assert await reopened.get("missing") is None
        await reopened.delete("key")
        await reopened.delete("missing")
        backend.fail = True
        await store.set("other", "memory-secret")
        assert store.memory_only
        assert await store.get("other") == "memory-secret"
        assert await store.get("missing") is None
        await store.delete("other")
        await store.close()
        with pytest.raises(ContractError):
            await store.get("key")
        failed = OSCredentialStore(redactor, backend)
        assert await failed.get("x") is None
        failed = OSCredentialStore(redactor, backend)
        with pytest.raises(ContractError):
            await failed.delete("x")
        assert failed.memory_only
        assert "top-secret" not in redactor.redact(
            "top-secret token=abc Bearer xyz https://user:pass@host"
        )

    asyncio.run(scenario())


def test_secret_redaction_across_stream_chunks() -> None:
    """Verify secret redaction across stream chunks.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    redactor = Redactor()
    redactor.register("secret-value")
    stream = StreamRedactor(redactor)
    outputs = [
        stream.feed("prefix secret-"),
        stream.feed("value\n"),
        stream.feed("next line\n"),
        stream.finish(),
    ]
    assert "secret-value" not in "".join(outputs)
    assert "[REDACTED]" in "".join(outputs)
    redactor.register("multi\nline")
    stream = StreamRedactor(redactor)
    assert "multi\nline" not in stream.feed("multi\nline\nmore\n") + stream.finish()


def test_diagnostic_retention_and_temporary_cleanup(tmp_path: Path) -> None:
    """Verify diagnostic retention and temporary cleanup.

    Parameters
    ----------
    tmp_path : Path
        Disposable directory managed by pytest.

    Returns
    -------
    None
    """
    now = [0.0]
    redactor = Redactor()
    store = DiagnosticStore(tmp_path / "logs", redactor, lambda: now[0])
    ordinary = store.record("task", status="completed")
    saved = store.record("tool", status="failed")
    store.save_permanently(saved)
    assert set(store.list()) == {ordinary, saved}
    now[0] = 7 * 24 * 3600
    assert store.list() == (saved,)
    assert not (store.root / f"{ordinary}.json").exists()
    assert not any(
        k in (store.root / f"{saved}.json").read_text()
        for k in ("prompt", "query", "content", "secret")
    )
    with pytest.raises(ValueError):
        store.record("private prompt", status="completed")
    with pytest.raises(ValueError):
        store.record("task", status="private content")
    with pytest.raises(ValueError):
        store.record("task", status="failed", duration_ms=-1)
    with pytest.raises(ValueError):
        store.delete("../escape")
    store.delete(saved)
    (store.root / "corrupt.json").write_text("corrupt")
    store.expire()
    assert not (store.root / "corrupt.json").exists()
    data = TaskTemporaryData(tmp_path)
    path = data.create("task")
    assert data.create("task") == path
    user_file = tmp_path / "user-code"
    user_file.write_text("retain")
    (path / "retrieved").write_text("raw data")
    data.cleanup("task")
    data.cleanup("task")
    data.create("other")
    data.close()
    assert user_file.read_text() == "retain"
