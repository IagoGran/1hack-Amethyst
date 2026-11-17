"""Regression coverage for public context sizes and inline-secret rejection."""

import asyncio

import pytest

from amethyst.adapters.models.base import ModelAdapter
from amethyst.configuration.connections import validate_connection
from amethyst.configuration.models import create_model_provider, create_pydantic_model
from amethyst.configuration.tools import create_tool
from amethyst.domain.contracts import Connection, ContractError, ErrorCode, JsonValue
from tests.support.fakes import MemoryCredentialStore


@pytest.mark.parametrize("kind", ["ollama", "openai", "gemini", "deepseek"])
def test_model_context_size_is_not_a_credential(kind: str) -> None:
    """Accept the desktop's explicit numeric context size for every provider.

    Parameters
    ----------
    kind : str
        Supported model-provider kind.

    Returns
    -------
    None
    """
    connection = Connection(
        "Qwen local",
        kind,
        {"model_id": "qwen2.5-coder:7b", "context_tokens": 8192},
        credential_ref=None if kind == "ollama" else "stored-key",
    )
    assert validate_connection(connection) == connection


@pytest.mark.parametrize("value", [0, -1, True, 8192.5, "8192"])
def test_invalid_context_size_is_still_rejected(value: JsonValue) -> None:
    """Require a positive integer despite the public-setting exception.

    Parameters
    ----------
    value : JsonValue
        Invalid context size supplied through settings.

    Returns
    -------
    None
    """
    with pytest.raises(ContractError) as error:
        validate_connection(
            Connection(
                "model", "ollama", {"model_id": "fixture", "context_tokens": value}
            )
        )
    assert error.value.code == ErrorCode.INVALID_INPUT


@pytest.mark.parametrize(
    "key", ["access_token", "api_key", "password", "context_tokens_extra"]
)
def test_context_size_does_not_hide_nested_credentials(key: str) -> None:
    """Retain recursive secret detection alongside an allowed context size.

    Parameters
    ----------
    key : str
        Credential-like key nested inside an otherwise supported option.

    Returns
    -------
    None
    """
    with pytest.raises(ContractError, match="credential service"):
        validate_connection(
            Connection(
                "model",
                "ollama",
                {
                    "model_id": {"nested": [{key: "fixture-secret"}]},
                    "context_tokens": 8192,
                },
            )
        )


@pytest.mark.parametrize(
    ("kind", "capacity"),
    [
        ("openai", 128_000),
        ("deepseek", 64_000),
        ("ollama", 32_000),
        ("gemini", 1_000_000),
    ],
)
def test_provider_factory_preserves_default_capacity(kind: str, capacity: int) -> None:
    """Retain provider-specific defaults through the shared model superclass.

    Parameters
    ----------
    kind : str
        Supported model provider.
    capacity : int
        Default capacity established by the existing adapter.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Resolve a provider without contacting its endpoint.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        credentials = MemoryCredentialStore()
        await credentials.set("fixture-key", "fixture-value")
        provider = await create_model_provider(
            Connection(
                "model", kind, {"model_id": "fixture"}, credential_ref="fixture-key"
            ),
            credentials,
        )
        assert isinstance(provider, ModelAdapter)
        assert (await provider.capabilities("fixture")).context_tokens == capacity

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("kind", "model_type"),
    [
        ("openai", "OpenAIResponsesModel"),
        ("gemini", "GoogleModel"),
        ("deepseek", "OpenAIChatModel"),
        ("ollama", "OllamaModel"),
    ],
)
def test_native_model_factory_uses_pydanticai_provider(
    kind: str, model_type: str
) -> None:
    """Construct a native PydanticAI model for each configured provider.

    Parameters
    ----------
    kind : str
        Supported model-provider kind.
    model_type : str
        Expected PydanticAI model class name.

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Build a provider model without making a network request.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        credentials = MemoryCredentialStore()
        await credentials.set("fixture-key", "fixture-value")
        model = await create_pydantic_model(
            Connection(
                "model",
                kind,
                {"model_id": "fixture"},
                credential_ref=None if kind == "ollama" else "fixture-key",
            ),
            credentials,
        )
        assert type(model).__name__ == model_type

    asyncio.run(scenario())


def test_custom_openai_endpoint_uses_chat_completions_model() -> None:
    """Use OpenAI-compatible chat completions for custom provider endpoints.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Construct the configured model without making a network request.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        credentials = MemoryCredentialStore()
        await credentials.set("fixture-key", "fixture-value")
        model = await create_pydantic_model(
            Connection(
                "compatible",
                "openai",
                {"model_id": "fixture", "endpoint": "http://localhost:9000/v1"},
                credential_ref="fixture-key",
            ),
            credentials,
        )
        assert type(model).__name__ == "OpenAIChatModel"

    asyncio.run(scenario())


def test_factories_reject_other_category_before_resolving_credentials() -> None:
    """Reject a mismatched role even when its credential reference is absent.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """

    async def scenario() -> None:
        """Exercise both category boundaries with unavailable secret references.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        credentials = MemoryCredentialStore()
        with pytest.raises(ContractError, match="not a model provider") as model:
            await create_model_provider(
                Connection(
                    "data", "sqlite", {"database": "fixture"}, credential_ref="absent"
                ),
                credentials,
            )
        with pytest.raises(ContractError, match="not a data tool") as tool:
            await create_tool(
                Connection(
                    "model", "ollama", {"model_id": "fixture"}, credential_ref="absent"
                ),
                credentials,
            )
        assert model.value.code == tool.value.code == ErrorCode.INVALID_INPUT

    asyncio.run(scenario())
