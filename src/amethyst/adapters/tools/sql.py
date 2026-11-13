"""Read-only SQL adapters with result and output bounds."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    OperationContext,
    Source,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

MAX_ROWS = 1_000


def _reject_write(
    action: int,
    arg1: str | None,
    arg2: str | None,
    database: str | None,
    trigger: str | None,
) -> int:
    """Allow only SQLite read and expression authorizer operations.

    Parameters
    ----------
    action : int
        SQLite authorizer operation code.
    arg1, arg2, database, trigger : str or None
        SQLite callback context, unused because the action code is sufficient.

    Returns
    -------
    int
        ``SQLITE_OK`` for reads or ``SQLITE_DENY`` for all other operations.
    """
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        getattr(sqlite3, "SQLITE_RECURSIVE", -1),
    }
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def _bounded_json(rows: list[dict[str, Any]], limit: int) -> tuple[str, bool]:
    """Encode rows within a byte limit while preserving valid JSON.

    Parameters
    ----------
    rows : list of dict
        Query rows to serialize.
    limit : int
        Maximum encoded byte count.

    Returns
    -------
    tuple
        JSON array and whether rows were removed to meet the limit.
    """
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
    raw = encoded.encode("utf-8")
    if len(raw) <= limit:
        return encoded, False
    # Keep valid JSON while trimming records to the byte budget.
    kept: list[dict[str, Any]] = []
    for row in rows:
        candidate = json.dumps(
            [*kept, row], ensure_ascii=False, separators=(",", ":"), default=str
        )
        if len(candidate.encode("utf-8")) > limit:
            break
        kept.append(row)
    return json.dumps(
        kept, ensure_ascii=False, separators=(",", ":"), default=str
    ), True


def _format_result(
    rows: list[dict[str, Any]], columns: list[str], limit: int
) -> tuple[str, bool]:
    """Serialize SQL metadata and rows within the output-byte limit.

    Parameters
    ----------
    rows : list of dict
        Result rows. The input list is not modified.
    columns : list of str
        Result column names.
    limit : int
        Maximum encoded output size.

    Returns
    -------
    tuple
        Bounded JSON object and truncation indicator.
    """
    truncated = False
    remaining_rows = list(rows)
    while remaining_rows:
        payload = json.dumps(
            {"columns": columns, "rows": remaining_rows},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
        if len(payload.encode("utf-8")) <= limit:
            return payload, truncated
        remaining_rows.pop()
        truncated = True
    payload = json.dumps({"columns": columns, "rows": []}, separators=(",", ":"))
    if len(payload.encode("utf-8")) > limit:
        payload = "{}" if limit >= 2 else ""
        truncated = True
    return payload, truncated


class SQLiteReadOnlyTool:
    def __init__(self, database: str | Path, connection_id: str = "sqlite") -> None:
        """Configure a read-only SQLite database connection.

        Parameters
        ----------
        database : str or pathlib.Path
            Source database path.
        connection_id : str, optional
            Safe source identifier included with query results.
        """
        self.database = Path(database).expanduser().resolve()
        self.connection_id = connection_id

    @property
    def definition(self) -> ToolDefinition:
        """Return the SQL query tool definition exposed to the agent."""
        return ToolDefinition(
            "sql.sqlite.query",
            "Run one read-only SQL query against the configured SQLite database.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            read_only=True,
        )

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Execute one read-only query and enforce row, time, and byte bounds.

        Parameters
        ----------
        call : ToolCall
            SQL tool call containing a query string.
        context : OperationContext
            Deadline and maximum output size.

        Returns
        -------
        ToolResult
            JSON columns and rows with source attribution.

        Raises
        ------
        ContractError
            For invalid input, denied writes, or query timeout/failure.
        """
        if call.name != self.definition.name or not isinstance(
            call.arguments.get("query"), str
        ):
            raise ContractError(ErrorCode.INVALID_INPUT, "A SQL query is required.")
        query = call.arguments.get("query")
        if not isinstance(query, str):
            raise ContractError(ErrorCode.INVALID_INPUT, "A SQL query is required.")
        deadline = time.monotonic() + max(0.01, context.timeout_seconds)
        try:
            rows, columns, truncated = await asyncio.wait_for(
                asyncio.to_thread(self._query, query, deadline),
                timeout=max(0.01, context.timeout_seconds),
            )
        except TimeoutError:
            raise ContractError(
                ErrorCode.TIMEOUT, "The SQLite query timed out.", transient=True
            ) from None
        except sqlite3.DatabaseError as exc:
            if "interrupted" in str(exc).lower():
                raise ContractError(
                    ErrorCode.TIMEOUT, "The SQLite query timed out.", transient=True
                ) from None
            if "not authorized" in str(exc).lower() or "readonly" in str(exc).lower():
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED, "Only read-only SQL is allowed."
                ) from None
            raise ContractError(
                ErrorCode.INVALID_INPUT, "The SQLite query could not be executed."
            ) from None
        content, byte_truncated = _format_result(
            rows, columns, max(0, context.output_limit_bytes)
        )
        return ToolResult(
            call.id, content, (Source(self.connection_id),), truncated or byte_truncated
        )

    def _query(
        self, query: str, deadline: float
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Run a query under SQLite read-only and authorizer protections.

        Parameters
        ----------
        query : str
            A single SQL statement.
        deadline : float
            Absolute monotonic deadline.

        Returns
        -------
        tuple
            Rows, column names, and row-limit truncation state.

        Raises
        ------
        ContractError
            If the query is empty.
        sqlite3.Error
            If SQLite rejects the statement or database.
        """
        if not query.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A SQL query is required.")
        uri = self.database.as_uri() + "?mode=ro"
        connection = sqlite3.connect(
            uri, uri=True, timeout=max(0.01, deadline - time.monotonic())
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.set_authorizer(_reject_write)
            connection.set_progress_handler(
                lambda: int(time.monotonic() >= deadline), 1_000
            )
            cursor = connection.execute(query)
            columns = [item[0] for item in (cursor.description or ())]
            rows = [
                dict(zip(columns, row, strict=True))
                for row in cursor.fetchmany(MAX_ROWS + 1)
            ]
            truncated = len(rows) > MAX_ROWS
            rows = rows[:MAX_ROWS]
            return rows, columns, truncated
        finally:
            connection.close()

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check whether the configured SQLite database can be read.

        Parameters
        ----------
        context : OperationContext
            Connection-test timeout.

        Returns
        -------
        ConnectionHealth
            Availability or a redacted failure outcome.
        """
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._health), context.timeout_seconds
            )
        except TimeoutError:
            return ConnectionHealth(
                False, "SQLite connection timed out.", ErrorCode.TIMEOUT
            )
        except (OSError, sqlite3.Error):
            return ConnectionHealth(
                False, "SQLite database is unavailable.", ErrorCode.UNAVAILABLE
            )
        return ConnectionHealth(True, "SQLite connection is available.")

    def _health(self) -> None:
        """Run a constant read-only health query against SQLite."""
        connection = sqlite3.connect(
            self.database.as_uri() + "?mode=ro", uri=True, timeout=2
        )
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()


class PostgreSQLReadOnlyTool:
    """PostgreSQL adapter using optional psycopg 3 and a read-only transaction."""

    def __init__(self, dsn: str, connection_id: str = "postgresql") -> None:
        """Configure PostgreSQL using a credential-bearing in-memory DSN.

        Parameters
        ----------
        dsn : str
            DSN assembled from validated settings and credential-store data.
        connection_id : str, optional
            Safe source identifier included with query results.
        """
        self._dsn = dsn
        self.connection_id = connection_id

    @property
    def definition(self) -> ToolDefinition:
        """Return the read-only PostgreSQL tool definition."""
        return ToolDefinition(
            "sql.postgresql.query",
            "Run one read-only SQL query against the configured PostgreSQL database.",
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            read_only=True,
        )

    async def execute(self, call: ToolCall, context: OperationContext) -> ToolResult:
        """Execute a bounded read-only PostgreSQL query.

        Parameters
        ----------
        call : ToolCall
            SQL tool call with one query string.
        context : OperationContext
            Deadline and output-byte limit.

        Returns
        -------
        ToolResult
            Bounded result data and database source attribution.

        Raises
        ------
        ContractError
            For invalid SQL, missing optional driver, or a provider failure.
        """
        query = call.arguments.get("query")
        if (
            call.name != self.definition.name
            or not isinstance(query, str)
            or not query.strip()
        ):
            raise ContractError(ErrorCode.INVALID_INPUT, "A SQL query is required.")
        try:
            rows, columns, truncated = await asyncio.wait_for(
                asyncio.to_thread(
                    self._query,
                    query,
                    context.output_limit_bytes,
                    context.timeout_seconds,
                ),
                timeout=max(0.01, context.timeout_seconds),
            )
        except TimeoutError:
            raise ContractError(
                ErrorCode.TIMEOUT, "The PostgreSQL query timed out.", transient=True
            ) from None
        except ImportError:
            raise ContractError(
                ErrorCode.UNAVAILABLE, "PostgreSQL support requires psycopg 3."
            ) from None
        except Exception as exc:
            if exc.__class__.__module__.startswith("psycopg"):
                raise _postgres_error(exc) from None
            raise
        content, byte_truncated = _format_result(
            rows, columns, max(0, context.output_limit_bytes)
        )
        return ToolResult(
            call.id,
            content,
            (Source(self.connection_id),),
            truncated or byte_truncated,
        )

    def _query(
        self, query: str, output_limit: int, timeout_seconds: float
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Run one statement inside a read-only PostgreSQL transaction.

        Parameters
        ----------
        query : str
            SQL statement to execute.
        output_limit : int
            Maximum serialized result size.
        timeout_seconds : float
            Server-side statement timeout.

        Returns
        -------
        tuple
            Rows, column names, and truncation indicator.

        Raises
        ------
        ImportError
            If psycopg 3 is not installed.
        psycopg.Error
            If connection or query execution fails.
        """
        import psycopg  # type: ignore[import-not-found]

        with psycopg.connect(
            self._dsn, connect_timeout=10, options="-c default_transaction_read_only=on"
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (str(max(1, int(timeout_seconds * 1000))),),
                )
                cursor.execute(query)
                columns = [item.name for item in (cursor.description or ())]
                rows = [
                    dict(zip(columns, row, strict=True))
                    for row in cursor.fetchmany(MAX_ROWS + 1)
                ]
        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        _, byte_truncated = _bounded_json(rows, max(0, output_limit))
        if byte_truncated:
            while (
                rows
                and len(
                    json.dumps(
                        {"columns": columns, "rows": rows},
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    ).encode("utf-8")
                )
                > output_limit
            ):
                rows.pop()
        return rows, columns, truncated or byte_truncated

    async def test_connection(self, context: OperationContext) -> ConnectionHealth:
        """Check PostgreSQL connection and classify safe failures.

        Parameters
        ----------
        context : OperationContext
            Connection-test timeout.

        Returns
        -------
        ConnectionHealth
            Availability and a stable, redacted error code when unavailable.
        """
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._health), timeout=context.timeout_seconds
            )
        except ImportError:
            return ConnectionHealth(
                False, "PostgreSQL support requires psycopg 3.", ErrorCode.UNAVAILABLE
            )
        except TimeoutError:
            return ConnectionHealth(
                False, "PostgreSQL connection timed out.", ErrorCode.TIMEOUT
            )
        except Exception as exc:
            if exc.__class__.__module__.startswith("psycopg"):
                failure = _postgres_error(exc)
                return ConnectionHealth(False, str(failure), failure.code)
            return ConnectionHealth(
                False, "PostgreSQL connection is unavailable.", ErrorCode.UNAVAILABLE
            )
        return ConnectionHealth(True, "PostgreSQL connection is available.")

    def _health(self) -> None:
        """Run a constant query in a read-only PostgreSQL connection."""
        import psycopg  # type: ignore[import-not-found]

        with psycopg.connect(
            self._dsn, connect_timeout=10, options="-c default_transaction_read_only=on"
        ) as conn:
            conn.execute("SELECT 1")


def _postgres_error(error: Exception) -> ContractError:
    """Map psycopg failures to safe domain error codes.

    Parameters
    ----------
    error : Exception
        Driver exception. Its message is intentionally not exposed.

    Returns
    -------
    ContractError
        Authentication, availability, or invalid-input classification.
    """
    sqlstate = getattr(error, "sqlstate", None)
    name = error.__class__.__name__
    if isinstance(sqlstate, str) and sqlstate.startswith("28"):
        return ContractError(
            ErrorCode.AUTHENTICATION, "PostgreSQL authentication failed."
        )
    if (isinstance(sqlstate, str) and sqlstate.startswith("08")) or name in {
        "OperationalError",
        "InterfaceError",
        "ConnectionTimeout",
    }:
        return ContractError(
            ErrorCode.UNAVAILABLE,
            "PostgreSQL is unavailable.",
            transient=True,
        )
    return ContractError(ErrorCode.INVALID_INPUT, "The PostgreSQL query failed.")
