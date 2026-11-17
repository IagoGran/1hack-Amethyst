"""Durable local repositories backed by an application-owned SQLite database."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from amethyst.adapters.codecs import (
    _decode_connection,
    _decode_conversation,
    _decode_skill,
    _encode_conversation,
    encode_record,
)
from amethyst.domain.contracts import (
    Connection,
    ContractError,
    Conversation,
    ErrorCode,
    Skill,
)
from amethyst.ports.persistence import Identified as Identified


@dataclass(frozen=True, slots=True)
class SQLiteRepositories:
    conversations: SQLiteRepository[Conversation]
    skills: SQLiteRepository[Skill]
    connections: SQLiteRepository[Connection]


def default_database_path() -> Path:
    """Return the per-user local data path without creating it.

    Parameters
    ----------
    None

    Returns
    -------
    Path
        Value produced by the operation.
    """
    data_home = os.environ.get("XDG_DATA_HOME")
    root = (
        Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    )
    return root / "amethyst" / "amethyst.sqlite3"


def create_sqlite_repositories(path: str | Path | None = None) -> SQLiteRepositories:
    """Create all durable repository adapters over one SQLite database.

    Parameters
    ----------
    path : str or pathlib.Path or None, optional
        Database location. Uses the per-user application path when omitted.

    Returns
    -------
    SQLiteRepositories
        Conversation, skill, and connection repositories.
    """
    database = path or default_database_path()
    return SQLiteRepositories(
        SQLiteConversationRepository(database),
        SQLiteSkillRepository(database),
        SQLiteConnectionRepository(database),
    )


class SQLiteRepository[T: Identified]:
    """An async upsert repository with detached JSON snapshots and migrations."""

    def __init__(
        self,
        path: str | Path,
        table: str,
        encode: Callable[[T], dict[str, object]],
        decode: Callable[[dict[str, object]], T],
    ) -> None:
        """Initialize a typed repository and ensure its database schema exists.

        Parameters
        ----------
        path : str or pathlib.Path
            SQLite database location.
        table : str
            One of the repository table names supported by this adapter.
        encode : Callable
            Convert a domain value into a JSON-compatible mapping.
        decode : Callable
            Convert a stored mapping into a domain value.

        Raises
        ------
        ValueError
            If ``table`` is not an approved repository table.

        Returns
        -------
        None
        """
        if table not in {"conversations", "skills", "connections"}:
            raise ValueError("Unsupported repository table.")
        self.path = Path(path).expanduser()
        self._table = table
        self._encode = encode
        self._decode = decode
        self._lock = asyncio.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection with foreign keys and a bounded lock wait.

        Returns
        -------
        sqlite3.Connection
            Open database connection owned by the caller.

        Parameters
        ----------
        None
        """
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        """Create the version-1 schema and restrict database file permissions.

        Raises
        ------
        RuntimeError
            If the database schema is newer than this application supports.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Database schema is newer than this application.")
            for table in ("conversations", "skills", "connections"):
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} "
                    "(id TEXT PRIMARY KEY NOT NULL, payload TEXT NOT NULL)"
                )
            connection.execute("PRAGMA user_version = 1")
        try:
            self.path.chmod(0o600)
        except OSError:
            # ACL-based platforms may not support POSIX mode bits.
            pass

    async def save(self, value: T) -> None:
        """Upsert a detached JSON snapshot of a domain record.

        Parameters
        ----------
        value : T
            Record to persist.

        Returns
        -------
        None
        """
        payload = json.dumps(self._encode(value), separators=(",", ":"))
        async with self._lock:
            await asyncio.to_thread(self._save, value.id, payload)

    def _save(self, item_id: str, payload: str) -> None:
        """Atomically upsert a serialized record in the configured table.

        Parameters
        ----------
        item_id : str
            Record identifier.
        payload : str
            Serialized record payload.

        Returns
        -------
        None
        """
        with closing(self._connect()) as connection, connection:
            connection.execute(
                f"INSERT INTO {self._table} (id, payload) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (item_id, payload),
            )

    async def load(self, item_id: str) -> T:
        """Load a detached record snapshot by identifier.

        Parameters
        ----------
        item_id : str
            Record identifier.

        Returns
        -------
        T
            Decoded domain record.

        Raises
        ------
        ContractError
            With ``NOT_FOUND`` for a missing ID or ``UNAVAILABLE`` for corrupt data.
        """
        async with self._lock:
            raw = await asyncio.to_thread(self._load, item_id)
        if raw is None:
            raise ContractError(ErrorCode.NOT_FOUND, "Record not found.")
        return self._deserialize(raw)

    def _deserialize(self, raw: str) -> T:
        """Decode stored JSON and translate corrupt records into a safe failure.

        Parameters
        ----------
        raw : str
            Serialized domain record.

        Returns
        -------
        T
            Detached decoded value.
        """
        try:
            return self._decode(json.loads(raw))
        except (KeyError, TypeError, ValueError):
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Stored record is invalid."
            ) from None

    def _load(self, item_id: str) -> str | None:
        """Read one serialized payload from SQLite.

        Parameters
        ----------
        item_id : str
            Record identifier.

        Returns
        -------
        str or None
            Stored JSON payload, or ``None`` when no record matches.
        """
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                f"SELECT payload FROM {self._table} WHERE id = ?", (item_id,)
            ).fetchone()
        return None if row is None else str(row[0])

    async def list(self) -> tuple[T, ...]:
        """Return detached records sorted by their identifiers.

        Returns
        -------
        tuple of T
            All records in deterministic identifier order.

        Raises
        ------
        ContractError
            If any stored row cannot be decoded.

        Parameters
        ----------
        None
        """
        async with self._lock:
            values = await asyncio.to_thread(self._list)
        return tuple(self._deserialize(value) for value in values)

    def _list(self) -> tuple[str, ...]:
        """Read serialized payloads in identifier order.

        Returns
        -------
        tuple of str
            Ordered record payloads.

        Parameters
        ----------
        None
        """
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                f"SELECT payload FROM {self._table} ORDER BY id"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    async def delete(self, item_id: str) -> None:
        """Delete a record; deleting a missing identifier is harmless.

        Parameters
        ----------
        item_id : str
            Record identifier.

        Returns
        -------
        None
        """
        async with self._lock:
            await asyncio.to_thread(self._delete, item_id)

    def _delete(self, item_id: str) -> None:
        """Delete a record using a parameterized SQLite statement.

        Parameters
        ----------
        item_id : str
            Record identifier.

        Returns
        -------
        None
        """
        with closing(self._connect()) as connection, connection:
            connection.execute(f"DELETE FROM {self._table} WHERE id = ?", (item_id,))


class SQLiteConversationRepository(SQLiteRepository[Conversation]):
    def __init__(self, path: str | Path) -> None:
        """Create the conversation repository for a shared database file.

        Parameters
        ----------
        path : str or pathlib.Path
            Application database location.

        Returns
        -------
        None
        """
        super().__init__(
            path, "conversations", _encode_conversation, _decode_conversation
        )


class SQLiteSkillRepository(SQLiteRepository[Skill]):
    def __init__(self, path: str | Path) -> None:
        """Create the skill repository for a shared database file.

        Parameters
        ----------
        path : str or pathlib.Path
            Application database location.

        Returns
        -------
        None
        """
        super().__init__(path, "skills", encode_record, _decode_skill)


class SQLiteConnectionRepository(SQLiteRepository[Connection]):
    def __init__(self, path: str | Path) -> None:
        """Create the connection repository for a shared database file.

        Parameters
        ----------
        path : str or pathlib.Path
            Application database location.

        Returns
        -------
        None
        """
        super().__init__(path, "connections", encode_record, _decode_connection)
