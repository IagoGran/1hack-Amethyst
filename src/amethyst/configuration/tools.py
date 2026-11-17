"""Resource-tool validation and factories, independent of model providers."""

from collections.abc import Callable
from urllib.parse import quote, urlsplit

from amethyst.adapters.tools.base import Tool
from amethyst.configuration.catalog import TOOL_KINDS, ConnectionKind
from amethyst.configuration.connection_validation import (
    _connection_kind,
    _required_text,
    _validate_endpoint,
    _validate_options,
)
from amethyst.domain.contracts import Connection, ContractError, ErrorCode
from amethyst.ports.credentials import CredentialStore


def _validate_kind_settings(kind: ConnectionKind, connection: Connection) -> None:
    """Check kind-specific required values and numeric bounds.

    Parameters
    ----------
    kind : ConnectionKind
        Parsed connector kind.
    connection : Connection
        Connection containing kind-specific options.

    Returns
    -------
    None

    Raises
    ------
    ContractError
        If required database, credential, or collection settings fail.
    """
    options = connection.options
    if kind == ConnectionKind.BRAVE and not connection.credential_ref:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "This connection requires a credential reference."
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


def validate_tool_connection(connection: Connection) -> Connection:
    """Validate resource settings without loading any optional clients.

    Parameters
    ----------
    connection : Connection
        SQL, search, or vector connection.

    Returns
    -------
    Connection
        Validated public settings.
    """
    kind = _connection_kind(connection)
    if kind not in TOOL_KINDS:
        raise ContractError(ErrorCode.INVALID_INPUT, "Connection is not a data tool.")
    _validate_options(kind, connection)
    _validate_endpoint(kind, connection.options)
    _validate_kind_settings(kind, connection)
    return connection


async def create_tool(connection: Connection, credentials: CredentialStore) -> Tool:
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
    connection = validate_tool_connection(connection)
    kind = ConnectionKind(connection.kind)
    secret = ""
    if connection.credential_ref:
        secret = await credentials.get(connection.credential_ref) or ""
        if not secret:
            raise ContractError(
                ErrorCode.AUTHENTICATION,
                "Configured connection credentials are unavailable.",
            )

    return TOOL_FACTORIES[kind](connection, secret)


def _create_sqlite(connection: Connection, secret: str = "") -> Tool:
    """Build a SQLite adapter from its configured database path.

    Parameters
    ----------
    connection : Connection
        Validated resource settings and persistent connector identity.
    secret : str
        Credential resolved separately; unused by SQLite.

    Returns
    -------
    Tool
        Configured adapter implementing the tool execution boundary.
    """
    from amethyst.adapters.tools.sql import SQLiteReadOnlyTool

    return SQLiteReadOnlyTool(
        _required_text(connection.options, "database"), connection.id
    )


def _create_postgresql(connection: Connection, secret: str) -> Tool:
    """Build PostgreSQL adapter settings using escaped credential values.

    Parameters
    ----------
    connection : Connection
        Validated resource settings and persistent connector identity.
    secret : str
        Credential resolved separately from public connection settings.

    Returns
    -------
    Tool
        Configured adapter implementing the tool execution boundary.
    """
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


def _create_brave(connection: Connection, secret: str) -> Tool:
    """Build Brave Search adapter from endpoint and result-limit settings.

    Parameters
    ----------
    connection : Connection
        Validated resource settings and persistent connector identity.
    secret : str
        Credential resolved separately from public connection settings.

    Returns
    -------
    Tool
        Configured adapter implementing the tool execution boundary.
    """
    from amethyst.adapters.tools.web_search import BraveSearchTool

    options = connection.options
    endpoint = options.get("endpoint", "https://api.search.brave.com/res/v1/web/search")
    max_results = options.get("max_results", 8)
    if not isinstance(endpoint, str):
        raise ContractError(ErrorCode.INVALID_INPUT, "Brave endpoint is invalid.")
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise ContractError(ErrorCode.INVALID_INPUT, "Brave result limit is invalid.")
    return BraveSearchTool(secret, endpoint=endpoint, max_results=max_results)


def _create_qdrant(connection: Connection, secret: str) -> Tool:
    """Load Qdrant on demand and configure the selected collection.

    Parameters
    ----------
    connection : Connection
        Validated resource settings and persistent connector identity.
    secret : str
        Credential resolved separately from public connection settings.

    Returns
    -------
    Tool
        Configured adapter implementing the tool execution boundary.
    """
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


def _create_chroma(connection: Connection, secret: str) -> Tool:
    """Load Chroma on demand and configure its HTTP collection client.

    Parameters
    ----------
    connection : Connection
        Validated resource settings and persistent connector identity.
    secret : str
        Credential resolved separately from public connection settings.

    Returns
    -------
    Tool
        Configured adapter implementing the tool execution boundary.
    """
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


def _create_milvus(connection: Connection, secret: str) -> Tool:
    """Load Milvus on demand and configure the selected collection.

    Parameters
    ----------
    connection : Connection
        Validated resource settings and persistent connector identity.
    secret : str
        Credential resolved separately from public connection settings.

    Returns
    -------
    Tool
        Configured adapter implementing the tool execution boundary.
    """
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


TOOL_FACTORIES: dict[ConnectionKind, Callable[[Connection, str], Tool]] = {
    ConnectionKind.SQLITE: _create_sqlite,
    ConnectionKind.POSTGRESQL: _create_postgresql,
    ConnectionKind.BRAVE: _create_brave,
    ConnectionKind.QDRANT: _create_qdrant,
    ConnectionKind.CHROMA: _create_chroma,
    ConnectionKind.MILVUS: _create_milvus,
}
