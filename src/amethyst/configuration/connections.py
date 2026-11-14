"""Compatibility entry points for categorized, secret-free connections."""

from amethyst.configuration.catalog import MODEL_KINDS, ConnectionKind
from amethyst.configuration.connection_validation import _connection_kind
from amethyst.configuration.models import (
    create_model_provider,
    validate_model_connection,
)
from amethyst.configuration.tools import create_tool, validate_tool_connection
from amethyst.domain.contracts import Connection

__all__ = [
    "ConnectionKind",
    "create_model_provider",
    "create_tool",
    "secret_free_config",
    "validate_connection",
]


def validate_connection(connection: Connection) -> Connection:
    """Dispatch validation to the model or resource configuration boundary.

    Parameters
    ----------
    connection : Connection
        Existing persisted connection; its serialized schema is unchanged.

    Returns
    -------
    Connection
        Validated model or resource settings.
    """
    if _connection_kind(connection) in MODEL_KINDS:
        return validate_model_connection(connection)
    return validate_tool_connection(connection)


def secret_free_config(connection: Connection) -> dict[str, object]:
    """Return validated non-secret settings without credential references.

    Parameters
    ----------
    connection : Connection
        Connection to validate and serialize.

    Returns
    -------
    dict
        Safe connection ID, kind, options, and enabled state.
    """
    validated = validate_connection(connection)
    return {
        "id": validated.id,
        "kind": validated.kind,
        "options": validated.options.copy(),
        "enabled": validated.enabled,
    }
