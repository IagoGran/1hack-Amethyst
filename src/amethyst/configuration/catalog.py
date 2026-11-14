"""Secret-free connection metadata shared by configuration and desktop forms."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class ConnectionCategory(StrEnum):
    MODEL = "model"
    TOOL = "tool"


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


@dataclass(frozen=True)
class ConnectionSpec:
    """Describe public form fields and the connector's agent result shape."""

    category: ConnectionCategory
    fields: tuple[str, ...]
    result_kind: str = "retrieval"
    content_field: str | None = None


_MODEL = ConnectionSpec(
    ConnectionCategory.MODEL, ("model_id", "endpoint", "context_tokens")
)
_VECTOR = ConnectionSpec(
    ConnectionCategory.TOOL, ("endpoint", "collection"), content_field="text"
)
CONNECTION_SPECS = MappingProxyType(
    {
        ConnectionKind.OPENAI: _MODEL,
        ConnectionKind.GEMINI: _MODEL,
        ConnectionKind.DEEPSEEK: _MODEL,
        ConnectionKind.OLLAMA: _MODEL,
        ConnectionKind.SQLITE: ConnectionSpec(
            ConnectionCategory.TOOL, ("database",), "sql"
        ),
        ConnectionKind.POSTGRESQL: ConnectionSpec(
            ConnectionCategory.TOOL, ("host", "database", "username", "port"), "sql"
        ),
        ConnectionKind.BRAVE: ConnectionSpec(
            ConnectionCategory.TOOL,
            ("endpoint", "max_results"),
            content_field="description",
        ),
        ConnectionKind.QDRANT: _VECTOR,
        ConnectionKind.MILVUS: _VECTOR,
        ConnectionKind.CHROMA: _VECTOR,
    }
)
MODEL_KINDS = frozenset(
    kind
    for kind, spec in CONNECTION_SPECS.items()
    if spec.category == ConnectionCategory.MODEL
)
TOOL_KINDS = frozenset(CONNECTION_SPECS) - MODEL_KINDS
NUMERIC_FIELDS = frozenset({"context_tokens", "port", "max_results"})
