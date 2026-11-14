"""Read-only SQL adapters with result and output bounds."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from amethyst.adapters.tools.sql_base import ReadOnlySQLTool, _format_result
from amethyst.domain.contracts import (
    ConnectionHealth,
    ContractError,
    ErrorCode,
    OperationContext,
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


class SQLiteReadOnlyTool(ReadOnlySQLTool):
    name = "sql.sqlite.query"
    database_label = "SQLite"

    def __init__(self, database: str | Path, connection_id: str = "sqlite") -> None:
        """Configure a read-only SQLite database connection.

        Parameters
        ----------
        database : str or pathlib.Path
            Source database path.
        connection_id : str, optional
            Safe source identifier included with query results.

        Returns
        -------
        None
        """
        self.database = Path(database).expanduser().resolve()
        self.connection_id = connection_id

    async def _execute_query(
        self, query: str, context: OperationContext
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Run the driver query and translate backend-specific failures safely.

        Parameters
        ----------
        query : str
            Validated SQL statement.
        context : OperationContext
            Query timeout and result-size policy.

        Returns
        -------
        tuple
            Rows, column names, and truncation state.
        """
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
        return rows, columns, truncated

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
        """Run a constant read-only health query against SQLite.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        connection = sqlite3.connect(
            self.database.as_uri() + "?mode=ro", uri=True, timeout=2
        )
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()


class PostgreSQLReadOnlyTool(ReadOnlySQLTool):
    """PostgreSQL adapter using optional psycopg 3 and a read-only transaction."""

    name = "sql.postgresql.query"
    database_label = "PostgreSQL"

    def __init__(self, dsn: str, connection_id: str = "postgresql") -> None:
        """Configure PostgreSQL using a credential-bearing in-memory DSN.

        Parameters
        ----------
        dsn : str
            DSN assembled from validated settings and credential-store data.
        connection_id : str, optional
            Safe source identifier included with query results.

        Returns
        -------
        None
        """
        self._dsn = dsn
        self.connection_id = connection_id

    async def _execute_query(
        self, query: str, context: OperationContext
    ) -> tuple[list[dict[str, Any]], list[str], bool]:
        """Run the driver query and translate backend-specific failures safely.

        Parameters
        ----------
        query : str
            Validated SQL statement.
        context : OperationContext
            Query timeout and result-size policy.

        Returns
        -------
        tuple
            Rows, column names, and truncation state.
        """
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
        return rows, columns, truncated

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
        content, byte_truncated = _format_result(rows, columns, max(0, output_limit))
        if byte_truncated:
            bounded = json.loads(content) if content else {}
            rows = bounded.get("rows", [])
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
        """Run a constant query in a read-only PostgreSQL connection.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
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
