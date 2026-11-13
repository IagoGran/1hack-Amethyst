"""Validated, secret-free connection settings and adapter factories."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from urllib.parse import quote, urlsplit

from amethyst.adapters.models.providers import (
    DeepSeekModelProvider,
    GeminiModelProvider,
    OllamaModelProvider,
    OpenAIModelProvider,
)
from amethyst.domain.contracts import Connection, ContractError, ErrorCode, JsonValue
from amethyst.ports.credentials import CredentialStore


class ConnectionKind(StrEnum):
    OPENAI = "openai"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    BRAVE = "brave"
    QDRANT = "qdrant"
    MILVUS = "milvus"
    CHROMA = "chroma"


_SECRET_KEYS = {
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "credential",
    "credentials",
}
_ALLOWED_OPTIONS = {
    ConnectionKind.OPENAI: {"endpoint", "model_id", "context_tokens"},
    ConnectionKind.GEMINI: {"endpoint", "model_id", "context_tokens"},
    ConnectionKind.DEEPSEEK: {"endpoint", "model_id", "context_tokens"},
    ConnectionKind.OLLAMA: {"endpoint", "model_id", "context_tokens"},
    ConnectionKind.SQLITE: {"database"},
    ConnectionKind.POSTGRESQL: {"host", "database", "username", "port"},
    ConnectionKind.BRAVE: {"endpoint", "max_results"},
    ConnectionKind.QDRANT: {"endpoint", "collection"},
    ConnectionKind.MILVUS: {"endpoint", "collection"},
    ConnectionKind.CHROMA: {"endpoint", "collection"},
}


def validate_connection(connection: Connection) -> Connection:
    """Validate connection settings without accepting inline credentials.

    Parameters
    ----------
    connection : Connection
        User-configured connector to validate.

    Returns
    -------
    Connection
        The same validated connection object.

    Raises
    ------
    ContractError
        If the kind, settings, endpoint, or credential reference is invalid.
    """
    kind = _connection_kind(connection)
    _validate_options(kind, connection)
    _validate_endpoint(kind, connection.options)
    _validate_kind_settings(kind, connection)
    return connection


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

    Raises
    ------
    ContractError
        If settings contain unknown keys or credential material.
    """
    options = connection.options
    unexpected = set(options) - _ALLOWED_OPTIONS[kind]
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


def _validate_kind_settings(kind: ConnectionKind, connection: Connection) -> None:
    """Check kind-specific required values and numeric bounds.

    Parameters
    ----------
    kind : ConnectionKind
        Parsed connector kind.
    connection : Connection
        Connection containing kind-specific options.

    Raises
    ------
    ContractError
        If required model, database, credential, or collection settings fail.
    """
    options = connection.options
    if (
        kind
        in {
            ConnectionKind.OPENAI,
            ConnectionKind.GEMINI,
            ConnectionKind.DEEPSEEK,
            ConnectionKind.BRAVE,
        }
        and not connection.credential_ref
    ):
        raise ContractError(
            ErrorCode.INVALID_INPUT, "This connection requires a credential reference."
        )
    if kind in {
        ConnectionKind.OPENAI,
        ConnectionKind.GEMINI,
        ConnectionKind.DEEPSEEK,
        ConnectionKind.OLLAMA,
    }:
        model_id = options.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
        context_tokens = options.get("context_tokens")
        if context_tokens is not None and (
            not isinstance(context_tokens, int)
            or isinstance(context_tokens, bool)
            or context_tokens <= 0
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Model context size must be a positive integer.",
            )
    if kind == ConnectionKind.SQLITE and not isinstance(options.get("database"), str):
        raise ContractError(
            ErrorCode.INVALID_INPUT, "SQLite connections require a database path."
        )
    if kind == ConnectionKind.POSTGRESQL and not connection.credential_ref:
        raise ContractError(
            ErrorCode.INVALID_INPUT,
            "PostgreSQL connections require a credential reference.",
        )
    if kind == ConnectionKind.POSTGRESQL:
        for field in ("host", "database", "username"):
            value = options.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(
                    ErrorCode.INVALID_INPUT,
                    f"PostgreSQL setting '{field}' is required.",
                )
        port = options.get("port", 5432)
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 1 <= port <= 65535
        ):
            raise ContractError(ErrorCode.INVALID_INPUT, "PostgreSQL port is invalid.")
    if kind == ConnectionKind.BRAVE:
        max_results = options.get("max_results", 8)
        if (
            not isinstance(max_results, int)
            or isinstance(max_results, bool)
            or max_results < 1
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Brave result limit is invalid."
            )
    if kind in {ConnectionKind.QDRANT, ConnectionKind.MILVUS, ConnectionKind.CHROMA}:
        collection = options.get("collection")
        if not isinstance(collection, str) or not collection.strip():
            raise ContractError(
                ErrorCode.INVALID_INPUT, "A vector collection is required."
            )


async def create_model_provider(connection: Connection, credentials: CredentialStore):
    """Create a model adapter using secret material from the credential store.

    Parameters
    ----------
    connection : Connection
        Validated model-provider connection settings.
    credentials : CredentialStore
        Credential lookup service.

    Returns
    -------
    Model provider
        Adapter implementing the shared model port.

    Raises
    ------
    ContractError
        If the connection is not a model provider or its secret is unavailable.
    """
    connection = validate_connection(connection)
    kind = ConnectionKind(connection.kind)
    options = connection.options
    secret = ""
    if connection.credential_ref:
        secret = await credentials.get(connection.credential_ref) or ""
    base_url = options.get("endpoint")
    if kind not in {
        ConnectionKind.OPENAI,
        ConnectionKind.GEMINI,
        ConnectionKind.DEEPSEEK,
        ConnectionKind.OLLAMA,
    }:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Connection is not a model provider."
        )
    if connection.credential_ref and not secret:
        raise ContractError(
            ErrorCode.AUTHENTICATION, "Configured model credentials are unavailable."
        )
    if base_url is not None and not isinstance(base_url, str):
        raise ContractError(ErrorCode.INVALID_INPUT, "Model endpoint is invalid.")
    context_tokens = options.get("context_tokens")
    if context_tokens is not None:
        if (
            not isinstance(context_tokens, int)
            or isinstance(context_tokens, bool)
            or context_tokens <= 0
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT,
                "Model context size must be a positive integer.",
            )
    if kind == ConnectionKind.OPENAI:
        return OpenAIModelProvider(
            secret,
            base_url=base_url,
            context_tokens=context_tokens if isinstance(context_tokens, int) else None,
        )
    if kind == ConnectionKind.GEMINI:
        return GeminiModelProvider(
            secret,
            base_url=base_url,
            context_tokens=(
                context_tokens if isinstance(context_tokens, int) else 1_000_000
            ),
        )
    if kind == ConnectionKind.DEEPSEEK:
        return DeepSeekModelProvider(
            secret,
            base_url=base_url,
            context_tokens=context_tokens if isinstance(context_tokens, int) else None,
        )
    return OllamaModelProvider(
        secret,
        base_url=base_url,
        context_tokens=context_tokens if isinstance(context_tokens, int) else None,
    )


async def create_tool(connection: Connection, credentials: CredentialStore):
    """Construct a configured data connector with optional clients loaded on demand.

    Parameters
    ----------
    connection : Connection
        Validated SQL, search, or vector-store connection settings.
    credentials : CredentialStore
        Credential lookup service.

    Returns
    -------
    Tool adapter
        Connector implementing the shared tool port.

    Raises
    ------
    ContractError
        If credentials or optional client support are unavailable.
    """
    connection = validate_connection(connection)
    kind = ConnectionKind(connection.kind)
    secret = ""
    if connection.credential_ref:
        secret = await credentials.get(connection.credential_ref) or ""
        if not secret:
            raise ContractError(
                ErrorCode.AUTHENTICATION,
                "Configured connection credentials are unavailable.",
            )

    factories = {
        ConnectionKind.SQLITE: lambda: _create_sqlite(connection),
        ConnectionKind.POSTGRESQL: lambda: _create_postgresql(connection, secret),
        ConnectionKind.BRAVE: lambda: _create_brave(connection, secret),
        ConnectionKind.QDRANT: lambda: _create_qdrant(connection, secret),
        ConnectionKind.CHROMA: lambda: _create_chroma(connection, secret),
        ConnectionKind.MILVUS: lambda: _create_milvus(connection, secret),
    }
    factory = factories.get(kind)
    if factory is not None:
        return factory()
    raise ContractError(ErrorCode.INVALID_INPUT, "Connection is not a data tool.")


def _create_sqlite(connection: Connection):
    """Build a SQLite adapter from its configured database path."""
    from amethyst.adapters.tools.sql import SQLiteReadOnlyTool

    return SQLiteReadOnlyTool(
        _required_text(connection.options, "database"), connection.id
    )


def _create_postgresql(connection: Connection, secret: str):
    """Build PostgreSQL adapter settings using escaped credential values."""
    from amethyst.adapters.tools.sql import PostgreSQLReadOnlyTool

    options = connection.options
    host = _required_text(options, "host")
    if any(char in host for char in "/@?#; \t\r\n"):
        raise ContractError(ErrorCode.INVALID_INPUT, "PostgreSQL host is invalid.")
    database = _required_text(options, "database")
    username = _required_text(options, "username")
    port = options.get("port", 5432)
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ContractError(ErrorCode.INVALID_INPUT, "PostgreSQL port is invalid.")
    dsn = (
        f"postgresql://{quote(username, safe='')}:{quote(secret, safe='')}@"
        f"{host}:{port}/{quote(database, safe='')}?sslmode=require"
    )
    return PostgreSQLReadOnlyTool(dsn, connection.id)


def _create_brave(connection: Connection, secret: str):
    """Build Brave Search adapter from endpoint and result-limit settings."""
    from amethyst.adapters.tools.web_search import BraveSearchTool

    options = connection.options
    endpoint = options.get("endpoint", "https://api.search.brave.com/res/v1/web/search")
    max_results = options.get("max_results", 8)
    if not isinstance(endpoint, str):
        raise ContractError(ErrorCode.INVALID_INPUT, "Brave endpoint is invalid.")
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise ContractError(ErrorCode.INVALID_INPUT, "Brave result limit is invalid.")
    return BraveSearchTool(secret, endpoint=endpoint, max_results=max_results)


def _create_qdrant(connection: Connection, secret: str):
    """Load Qdrant on demand and configure the selected collection."""
    from amethyst.adapters.tools.vector import QdrantTool

    try:
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    except ImportError:
        raise ContractError(
            ErrorCode.UNAVAILABLE, "Qdrant support requires qdrant-client."
        ) from None
    endpoint = connection.options.get("endpoint", "http://127.0.0.1:6333")
    client = QdrantClient(
        url=endpoint if isinstance(endpoint, str) else "http://127.0.0.1:6333",
        api_key=secret or None,
        timeout=30,
    )
    return QdrantTool(_required_text(connection.options, "collection"), client)


def _create_chroma(connection: Connection, secret: str):
    """Load Chroma on demand and configure its HTTP collection client."""
    from amethyst.adapters.tools.vector import ChromaTool

    try:
        import chromadb  # type: ignore[import-not-found]
    except ImportError:
        raise ContractError(
            ErrorCode.UNAVAILABLE, "ChromaDB support requires chromadb."
        ) from None
    endpoint = connection.options.get("endpoint", "http://127.0.0.1:8000")
    url = endpoint if isinstance(endpoint, str) else "http://127.0.0.1:8000"
    parsed = urlsplit(url)
    client = chromadb.HttpClient(
        host=parsed.hostname,
        port=parsed.port or 8000,
        ssl=parsed.scheme == "https",
        headers={"Authorization": f"Bearer {secret}"} if secret else None,
    )
    return ChromaTool(_required_text(connection.options, "collection"), client)


def _create_milvus(connection: Connection, secret: str):
    """Load Milvus on demand and configure the selected collection."""
    from amethyst.adapters.tools.vector import MilvusTool

    try:
        from pymilvus import MilvusClient  # type: ignore[import-not-found]
    except ImportError:
        raise ContractError(
            ErrorCode.UNAVAILABLE, "Milvus support requires pymilvus."
        ) from None
    endpoint = connection.options.get("endpoint", "http://127.0.0.1:19530")
    client = MilvusClient(
        uri=endpoint if isinstance(endpoint, str) else "http://127.0.0.1:19530",
        token=secret or None,
    )
    return MilvusTool(_required_text(connection.options, "collection"), client)


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
