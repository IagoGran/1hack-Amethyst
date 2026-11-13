"""Stdlib SSE and NDJSON transport for model adapters."""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.error
import urllib.request
from collections.abc import AsyncGenerator, Callable
from typing import Any, cast

from amethyst.domain.contracts import ContractError, ErrorCode


async def stream_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    *,
    line_delimited_json: bool = False,
) -> AsyncGenerator[dict[str, Any]]:
    """Yield decoded JSON events from an HTTP streaming response.

    Parameters
    ----------
    url : str
        Streaming endpoint URL.
    headers : dict[str, str]
        Request headers. Callers must not log secret-bearing values.
    payload : dict[str, Any]
        JSON request body.
    timeout : float
        Socket timeout in seconds.
    line_delimited_json : bool, optional
        Parse each non-empty line as JSON instead of reading SSE ``data:`` lines.

    Yields
    ------
    dict[str, Any]
        One decoded event at a time.

    Raises
    ------
    ContractError
        If the endpoint returns an HTTP or stream-format error.
    """
    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    stopped = threading.Event()
    response_holder: list[object] = []
    publish = _event_publisher(loop, queue)
    worker = asyncio.create_task(
        asyncio.to_thread(
            _read_response,
            url,
            headers,
            payload,
            timeout,
            line_delimited_json,
            stopped,
            response_holder,
            publish,
        )
    )
    try:
        async for event in _consume_events(queue):
            yield event
    finally:
        stopped.set()
        _close_response(response_holder)
        if not worker.done():
            worker.cancel()


async def _consume_events(
    queue: asyncio.Queue[tuple[str, object]],
) -> AsyncGenerator[dict[str, Any]]:
    """Translate worker messages into events or safe contract errors.

    Parameters
    ----------
    queue : asyncio.Queue
        Queue populated by the blocking HTTP worker.

    Yields
    ------
    dict[str, Any]
        Decoded provider event.

    Raises
    ------
    ContractError
        For a worker-reported transport or response error.
    """
    while True:
        kind, value = await queue.get()
        if kind == "data":
            yield cast(dict[str, Any], value)
        elif kind == "error":
            _raise_stream_error(value)
        else:
            return


def _raise_stream_error(value: object) -> None:
    """Raise a safe provider transport error from the worker result.

    Parameters
    ----------
    value : object
        Error tuple emitted by ``_read_response``.

    Raises
    ------
    ContractError
        Always, with a redacted message and stable error code.
    """
    code, transient, retry_after = cast(tuple[ErrorCode, bool, float | None], value)
    message = (
        "Model authentication failed."
        if code == ErrorCode.AUTHENTICATION
        else "Model service request failed."
    )
    raise ContractError(
        code,
        message,
        transient=transient,
        retry_after_seconds=retry_after,
    )


def _event_publisher(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[tuple[str, object]],
) -> Callable[[str, object], None]:
    """Create a callback that safely schedules events on the asyncio loop.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        Owning event loop.
    queue : asyncio.Queue
        Destination queue consumed by ``stream_json``.

    Returns
    -------
    Callable[[str, object], None]
        Thread-safe event publisher.
    """

    def publish(kind: str, value: object) -> None:
        """Schedule one typed event on the owning asyncio loop."""
        loop.call_soon_threadsafe(queue.put_nowait, (kind, value))

    return publish


def _read_response(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    line_delimited_json: bool,
    stopped: threading.Event,
    response_holder: list[object],
    publish: Callable[[str, object], None],
) -> None:
    """Read the blocking HTTP stream and publish decoded events.

    Parameters
    ----------
    url : str
        Provider endpoint.
    headers : dict[str, str]
        Request headers.
    payload : dict[str, Any]
        JSON request body.
    timeout : float
        Socket timeout in seconds.
    line_delimited_json : bool
        Select NDJSON parsing when true; otherwise parse SSE.
    stopped : threading.Event
        Cancellation signal set by the async consumer.
    response_holder : list[object]
        Mutable holder used to close the active response on cancellation.
    publish : Callable[[str, object], None]
        Thread-safe event callback.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        _read_successful_response(
            request,
            timeout,
            line_delimited_json,
            stopped,
            response_holder,
            publish,
        )
    except urllib.error.HTTPError as error:
        publish("error", _http_error(error))
    except TimeoutError:
        publish("error", (ErrorCode.TIMEOUT, True, None))
    except OSError:
        publish("error", (ErrorCode.UNAVAILABLE, True, None))
    except ValueError:
        publish("error", (ErrorCode.INVALID_INPUT, False, None))
    except Exception:
        publish("error", (ErrorCode.UNAVAILABLE, False, None))


def _read_successful_response(
    request: urllib.request.Request,
    timeout: float,
    line_delimited_json: bool,
    stopped: threading.Event,
    response_holder: list[object],
    publish: Callable[[str, object], None],
) -> None:
    """Read and publish events from a successful HTTP response.

    Parameters
    ----------
    request : urllib.request.Request
        Prepared HTTP request.
    timeout : float
        Socket timeout in seconds.
    line_delimited_json : bool
        Select NDJSON parsing when true; otherwise parse SSE.
    stopped : threading.Event
        Cancellation signal.
    response_holder : list[object]
        Mutable response reference for cancellation cleanup.
    publish : Callable[[str, object], None]
        Thread-safe event callback.
    """
    response = urllib.request.urlopen(request, timeout=max(0.1, timeout))
    response_holder.append(response)
    with response:
        for raw_line in response:
            if stopped.is_set():
                break
            event, done = _decode_stream_line(raw_line, line_delimited_json)
            if done:
                break
            if event is not None:
                publish("data", event)
    publish("done", None)


def _decode_stream_line(
    raw_line: bytes, line_delimited_json: bool
) -> tuple[dict[str, Any] | None, bool]:
    """Decode one SSE or NDJSON line, ignoring non-event SSE lines.

    Parameters
    ----------
    raw_line : bytes
        Raw line received from the response.
    line_delimited_json : bool
        Parse each non-empty line as JSON when true.

    Returns
    -------
    tuple
        Decoded event and completion flag. Empty event slots are ``None``.

    Raises
    ------
    json.JSONDecodeError
        If an event line contains invalid JSON.
    """
    line = raw_line.decode("utf-8", errors="replace").strip()
    if not line:
        return None, False
    if line_delimited_json:
        body = line
    elif line.startswith("data:"):
        body = line[5:].strip()
    else:
        return None, False
    if body == "[DONE]":
        return None, True
    event = json.loads(body)
    if not isinstance(event, dict):
        raise json.JSONDecodeError("Expected JSON object", body, 0)
    return cast(dict[str, Any], event), False


def _http_error(error: urllib.error.HTTPError) -> tuple[ErrorCode, bool, float | None]:
    """Map an HTTP status to a stable, secret-free error tuple.

    Parameters
    ----------
    error : urllib.error.HTTPError
        HTTP failure returned by the provider.

    Returns
    -------
    tuple
        Error code, transient flag, and optional retry delay.
    """
    retry = error.code >= 500 or error.code == 429
    after = _retry_after(error.headers.get("Retry-After"))
    if error.code in (401, 403):
        code = ErrorCode.AUTHENTICATION
    elif error.code == 408:
        code = ErrorCode.TIMEOUT
    elif error.code in (400, 404, 422):
        code = ErrorCode.INVALID_INPUT
    else:
        code = ErrorCode.UNAVAILABLE
    return code, retry, after


def _close_response(response_holder: list[object]) -> None:
    """Close the active response during async cancellation.

    Parameters
    ----------
    response_holder : list[object]
        Mutable holder populated by ``_read_successful_response``.
    """
    if not response_holder:
        return
    try:
        response_holder[0].close()  # type: ignore[attr-defined]
    except OSError:
        pass


def _retry_after(value: str | None) -> float | None:
    """Parse a numeric ``Retry-After`` header value.

    Parameters
    ----------
    value : str or None
        Header value expressed as a number of seconds.

    Returns
    -------
    float or None
        Non-negative delay, or ``None`` when absent or invalid.
    """
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
