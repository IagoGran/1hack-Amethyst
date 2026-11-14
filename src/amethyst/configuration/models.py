"""Model-only settings validation and provider construction."""

from amethyst.adapters.models.base import ModelAdapter
from amethyst.adapters.models.providers import (
    DeepSeekModelProvider,
    GeminiModelProvider,
    OllamaModelProvider,
    OpenAIModelProvider,
)
from amethyst.configuration.catalog import MODEL_KINDS, ConnectionKind
from amethyst.configuration.connection_validation import (
    _connection_kind,
    _validate_endpoint,
    _validate_options,
)
from amethyst.domain.contracts import Connection, ContractError, ErrorCode
from amethyst.ports.credentials import CredentialStore
from amethyst.ports.model_provider import ModelProvider

PROVIDER_FACTORIES: dict[ConnectionKind, type[ModelAdapter]] = {
    ConnectionKind.OPENAI: OpenAIModelProvider,
    ConnectionKind.GEMINI: GeminiModelProvider,
    ConnectionKind.DEEPSEEK: DeepSeekModelProvider,
    ConnectionKind.OLLAMA: OllamaModelProvider,
}


def validate_model_connection(connection: Connection) -> Connection:
    """Validate a model connection independently of resource tools.

    Parameters
    ----------
    connection : Connection
        Public provider settings and an optional credential reference.

    Returns
    -------
    Connection
        Validated settings with no credentials resolved.
    """
    kind = _connection_kind(connection)
    if kind not in MODEL_KINDS:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Connection is not a model provider."
        )
    _validate_options(kind, connection)
    _validate_endpoint(kind, connection.options)
    if kind != ConnectionKind.OLLAMA and not connection.credential_ref:
        raise ContractError(
            ErrorCode.INVALID_INPUT, "This connection requires a credential reference."
        )
    model_id = connection.options.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ContractError(ErrorCode.INVALID_INPUT, "A model ID is required.")
    context_tokens = connection.options.get("context_tokens")
    if context_tokens is not None and (
        not isinstance(context_tokens, int)
        or isinstance(context_tokens, bool)
        or context_tokens <= 0
    ):
        raise ContractError(
            ErrorCode.INVALID_INPUT, "Model context size must be a positive integer."
        )
    return connection


async def create_model_provider(
    connection: Connection, credentials: CredentialStore
) -> ModelProvider:
    """Construct a provider using model settings and separately stored secrets.

    Parameters
    ----------
    connection : Connection
        Model connection to validate and resolve.
    credentials : CredentialStore
        Secure secret lookup service.

    Returns
    -------
    ModelProvider
        Provider implementing generation and capability discovery.
    """
    validate_model_connection(connection)
    secret = ""
    if connection.credential_ref:
        secret = await credentials.get(connection.credential_ref) or ""
        if not secret:
            raise ContractError(
                ErrorCode.AUTHENTICATION,
                "Configured model credentials are unavailable.",
            )
    endpoint = connection.options.get("endpoint")
    context_tokens = connection.options.get("context_tokens")
    factory = PROVIDER_FACTORIES[ConnectionKind(connection.kind)]
    base_url = endpoint if isinstance(endpoint, str) else None
    if isinstance(context_tokens, int):
        return factory(secret, base_url=base_url, context_tokens=context_tokens)
    return factory(secret, base_url=base_url)
