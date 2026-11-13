"""Preview-only SQLite implementation of the conversation repository port."""

import json
import sqlite3
from contextlib import AbstractContextManager, closing
from pathlib import Path
from typing import Literal, cast

from amethyst.domain.contracts import (
    ContractError,
    Conversation,
    ErrorCode,
    JsonValue,
    Message,
    ToolCall,
)


class PreviewSQLiteConversationRepository:
    """Persist conversation DTOs locally for the A3 preview only."""

    def __init__(self, database_path: Path) -> None:
        """Create the preview database and its single conversation table."""
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._database_path)) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conversations "
                "(id TEXT PRIMARY KEY, title TEXT NOT NULL, messages TEXT NOT NULL)"
            )
            connection.commit()

    async def save(self, value: Conversation) -> None:
        """Upsert a detached conversation snapshot and its ordered messages."""
        encoded = json.dumps(
            [self._encode_message(message) for message in value.messages],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id, title, messages) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, "
                "messages=excluded.messages",
                (value.id, value.title, encoded),
            )
            connection.commit()

    async def load(self, item_id: str) -> Conversation:
        """Load one conversation or raise the repository's not-found error."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, title, messages FROM conversations WHERE id = ?",
                (item_id,),
            ).fetchone()
        if row is None:
            raise ContractError(ErrorCode.NOT_FOUND, "Conversation was not found.")
        messages = json.loads(row[2])
        return Conversation(
            row[0], row[1], tuple(self._decode_message(m) for m in messages)
        )

    async def list(self) -> tuple[Conversation, ...]:
        """Return detached conversation snapshots ordered by repository contract."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, title, messages FROM conversations ORDER BY id"
            ).fetchall()
        return tuple(
            Conversation(
                row[0],
                row[1],
                tuple(self._decode_message(item) for item in json.loads(row[2])),
            )
            for row in rows
        )

    async def delete(self, item_id: str) -> None:
        """Delete a conversation idempotently by its stable ID."""
        with self._connect() as connection:
            connection.execute("DELETE FROM conversations WHERE id = ?", (item_id,))
            connection.commit()

    def _connect(self) -> AbstractContextManager[sqlite3.Connection]:
        """Yield a short-lived SQLite connection and always close it."""
        return closing(sqlite3.connect(self._database_path))

    @staticmethod
    def _encode_message(message: Message) -> dict[str, JsonValue]:
        """Convert a message and nested tool calls to JSON-safe values."""
        return {
            "role": message.role,
            "content": message.content,
            "tool_call_id": message.tool_call_id,
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in message.tool_calls
            ],
        }

    @staticmethod
    def _decode_message(value: dict[str, JsonValue]) -> Message:
        """Rebuild a typed message and its immutable tool-call tuple."""
        calls = cast(list[dict[str, JsonValue]], value["tool_calls"])
        return Message(
            role=cast(Literal["system", "user", "assistant", "tool"], value["role"]),
            content=cast(str, value["content"]),
            tool_call_id=cast(str | None, value["tool_call_id"]),
            tool_calls=tuple(
                ToolCall(
                    id=cast(str, call["id"]),
                    name=cast(str, call["name"]),
                    arguments=cast(dict[str, JsonValue], call["arguments"]),
                )
                for call in calls
            ),
        )
