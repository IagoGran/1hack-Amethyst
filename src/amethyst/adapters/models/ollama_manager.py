"""Local-only Ollama model listing and pull operations."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from amethyst.domain.contracts import ContractError, ErrorCode


def _local_endpoint(endpoint: str | None) -> str:
    """Validate that Ollama management targets a loopback endpoint only.

    Parameters
    ----------
    endpoint : str or None
        Configured Ollama base URL or its local default.

    Returns
    -------
    str
        Validated local base URL.

    Raises
    ------
    ContractError
        If the address is not loopback or is malformed.
    """
    base = (endpoint or "http://localhost:11434").rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username
        or parsed.password
    ):
        raise ContractError(
            ErrorCode.PERMISSION_DENIED,
            "Ollama model management requires a local HTTP endpoint.",
        )
    return base


def list_models(endpoint: str | None = None) -> tuple[str, ...]:
    """Return names of locally installed Ollama models.

    Parameters
    ----------
    endpoint : str or None
        Configured local Ollama endpoint.

    Returns
    -------
    tuple of str
        Installed local model names.

    Raises
    ------
    ContractError
        If Ollama is unavailable or returns an invalid response.
    """
    base = _local_endpoint(endpoint)
    try:
        with urlopen(base + "/api/tags", timeout=3) as response:
            data = json.loads(response.read(1_000_000))
        models = data.get("models", [])
        if not isinstance(models, list):
            raise ValueError("invalid model list")
        return tuple(
            str(model["name"])
            for model in models
            if isinstance(model, dict) and isinstance(model.get("name"), str)
        )
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise ContractError(
            ErrorCode.UNAVAILABLE, "Unable to query the local Ollama service."
        ) from error


def pull_model(
    name: str,
    endpoint: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Pull one named model and report streamed status text.

    Parameters
    ----------
    name : str
        Local Ollama model identifier.
    endpoint : str or None
        Configured local Ollama endpoint.
    progress : Callable or None
        Optional callback receiving safe Ollama status lines.

    Returns
    -------
    None

    Raises
    ------
    ContractError
        If the local service rejects the request or becomes unavailable.
    """
    if not name.strip() or len(name) > 160:
        raise ContractError(ErrorCode.INVALID_INPUT, "Enter a valid model name.")
    base = _local_endpoint(endpoint)
    request = Request(
        base + "/api/pull",
        data=json.dumps({"name": name.strip(), "stream": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:
            for line in response:
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict) and isinstance(item.get("error"), str):
                    raise ContractError(
                        ErrorCode.UNAVAILABLE, "Ollama reported a model pull error."
                    )
                status = item.get("status") if isinstance(item, dict) else None
                if isinstance(status, str) and progress:
                    progress(status[:200])
    except ContractError:
        raise
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise ContractError(
            ErrorCode.UNAVAILABLE, "The local Ollama model pull failed."
        ) from error
