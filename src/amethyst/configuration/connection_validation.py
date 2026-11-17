"""Shared secret and endpoint validation without adapter dependencies."""

from collections.abc import Mapping
from urllib.parse import urlsplit

from amethyst.configuration.catalog import CONNECTION_SPECS, ConnectionKind
from amethyst.domain.contracts import Connection, ContractError, ErrorCode, JsonValue

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "credential",
    "credentials",
}


def _connection_kind(connection: Connection) -> ConnectionKind:
    """Parse a connection kind or raise a safe validation error.

    Parameters
    ----------
    connection : Connection
        Connection with a string kind.

    Returns
    -------
    ConnectionKind
        Supported connector kind.
    """
    try:
        return ConnectionKind(connection.kind)
    except ValueError:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Unsupported connection type."
        ) from None


def _validate_options(kind: ConnectionKind, connection: Connection) -> None:
    """Reject unsupported fields and recursively detect inline secrets.

    Parameters
    ----------
    kind : ConnectionKind
        Parsed connector kind.
    connection : Connection
        Connector settings to inspect.

    Returns
    -------
    None

    Raises
    ------
    ContractError
        If settings contain unknown keys or credential material.
    """
    options = connection.options
    unexpected = set(options) - set(CONNECTION_SPECS[kind].fields)
    if unexpected:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Connection has unsupported settings."
        )

    if _contains_secret_key(options):
        raise ContractError(
            ErrorCode.INVALID_INPUT,
            "Store credentials in the credential service, not connection settings.",
        )


def _contains_secret_key(value: object) -> bool:
    """Return whether a nested mapping contains a credential-like key.

    Parameters
    ----------
    value : object
        Arbitrary nested setting value.

    Returns
    -------
    bool
        True when any nested key appears to contain a secret.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            # Model context size is a public numeric setting, not an access token.
            if (
                lowered == "context_tokens"
                and isinstance(child, int)
                and not isinstance(child, bool)
            ):
                continue
            if lowered in _SECRET_KEYS or any(
                marker in lowered
                for marker in ("password", "secret", "token", "api_key")
            ):
                return True
            if _contains_secret_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_key(child) for child in value)
    return False


def _validate_endpoint(kind: ConnectionKind, options: Mapping[str, JsonValue]) -> None:
    """Validate an optional HTTP endpoint and reject embedded credentials.

    Parameters
    ----------
    kind : ConnectionKind
        Connector kind, used to document endpoint-bearing adapters.
    options : Mapping
        Connector options.

    Returns
    -------
    None

    Raises
    ------
    ContractError
        If an endpoint is malformed or includes credentials/query data.
    """
    endpoint = options.get("endpoint")
    if endpoint is not None:
        if not isinstance(endpoint, str):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Connection endpoint must be text."
            )
        parsed = urlsplit(endpoint)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Endpoints cannot contain credentials or query parameters.",
            )
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Connection endpoint must be an HTTP(S) URL."
            )
    del kind


def _required_text(options: Mapping[str, JsonValue], name: str) -> str:
    """Return a required non-empty text option.

    Parameters
    ----------
    options : Mapping
        Connector settings.
    name : str
        Required setting name.

    Returns
    -------
    str
        Non-empty setting value.

    Raises
    ------
    ContractError
        If the setting is absent, not text, or blank.
    """
    value = options.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(
            ErrorCode.INVALID_INPUT, f"Connection setting '{name}' is required."
        )
    return value
