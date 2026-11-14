"""Serialization for durable conversation, skill, and connection records."""

from dataclasses import asdict
from typing import Any, cast

from amethyst.domain.contracts import (
    Connection,
    Conversation,
    JsonValue,
    Message,
    Skill,
    ToolCall,
)


def decode_message(data: dict[str, Any]) -> Message:
    """Reconstruct a message with immutable nested tool-call values.

    Parameters
    ----------
    data : dict
        Stored message fields.

    Returns
    -------
    Message
        Reconstructed conversation message.
    """
    return Message(
        role=data["role"],
        content=data["content"],
        tool_call_id=data.get("tool_call_id"),
        tool_calls=tuple(ToolCall(**call) for call in data.get("tool_calls", [])),
    )


def _encode_conversation(value: Conversation) -> dict[str, object]:
    """Serialize a conversation and its ordered messages.

    Parameters
    ----------
    value : Conversation
        Conversation record.

    Returns
    -------
    dict
        JSON-compatible representation.
    """
    return {
        "id": value.id,
        "title": value.title,
        "messages": [encode_record(message) for message in value.messages],
    }


def _decode_conversation(data: dict[str, object]) -> Conversation:
    """Restore a conversation and nested tool calls from JSON data.

    Parameters
    ----------
    data : dict
        Stored conversation mapping.

    Returns
    -------
    Conversation
        Reconstructed conversation value.

    Raises
    ------
    KeyError, TypeError
        If required fields or nested data have invalid shapes.
    """
    raw_messages = data.get("messages", [])
    if not isinstance(raw_messages, list):
        raise TypeError("messages must be a list")
    messages = tuple(decode_message(raw) for raw in raw_messages)
    return Conversation(str(data["id"]), str(data["title"]), messages)


def _decode_skill(data: dict[str, object]) -> Skill:
    """Restore a skill from its stored mapping.

    Parameters
    ----------
    data : dict
        Stored skill fields.

    Returns
    -------
    Skill
        Reconstructed skill value.
    """
    return Skill(
        id=str(data["id"]),
        name=str(data["name"]),
        instructions=str(data["instructions"]),
        enabled=bool(data.get("enabled", True)),
        condition=cast(str | None, data.get("condition")),
    )


def _decode_connection(data: dict[str, object]) -> Connection:
    """Restore a connection configuration from stored JSON fields.

    Parameters
    ----------
    data : dict
        Stored connection fields.

    Returns
    -------
    Connection
        Reconstructed connection value.
    """
    return Connection(
        id=str(data["id"]),
        kind=str(data["kind"]),
        options=cast(dict[str, JsonValue], data["options"]),
        enabled=bool(data.get("enabled", True)),
        credential_ref=cast(str | None, data.get("credential_ref")),
    )


def encode_record(value: Skill | Connection | Message) -> dict[str, object]:
    """Serialize simple saved records using their dataclass field representation.

    Parameters
    ----------
    value : Skill, Connection, or Message
        Saved settings, reusable instructions, or conversation messages.

    Returns
    -------
    dict
        Detached JSON-compatible fields.
    """
    return asdict(value)
