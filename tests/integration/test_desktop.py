"""Exercise the real Qt/agent/HTTP-adapter/persistence boundary without services."""

import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit

from amethyst.domain.contracts import Connection, JsonValue, Skill
from amethyst.ui.desktop import DesktopWindow
from amethyst.ui.desktop_worker import DesktopWorker


class ModelServer(ThreadingHTTPServer):
    """Local Ollama/Brave protocol fixture; no external network access."""

    requests: list[dict]
    tool_kind: str


class Handler(BaseHTTPRequestHandler):
    """Answer deterministic HTTP requests from the production adapters."""

    def log_message(self, format: str, *args) -> None:
        """Keep fixture requests out of logs.

        Parameters
        ----------
        format : str
            Ignored server log template.
        *args : tuple
            Ignored log fields.

        Returns
        -------
        None
        """

    def do_POST(self) -> None:
        """Return a tool call followed by an answer after the tool result.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        server = self.server
        assert isinstance(server, ModelServer)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        server.requests.append(body)
        if self.path.endswith("/chat/completions"):
            has_tool_result = any(
                message["role"] == "tool" for message in body["messages"]
            )
            if has_tool_result:
                deltas: list[dict[str, object]] = [{"content": "The result is 42.\n"}]
                finish_reason = "stop"
            else:
                name = next(
                    tool["function"]["name"]
                    for tool in body["tools"]
                    if tool["function"]["name"].startswith(server.tool_kind)
                )
                arguments = (
                    {"query": "SELECT value FROM sample"}
                    if server.tool_kind == "sqlite"
                    else {"query": "fixture"}
                )
                deltas = [
                    {
                        "content": "I will read the configured source.\n",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "read-source",
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    }
                ]
                finish_reason = "tool_calls"
            chunks = [
                {
                    "id": "fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {
                            "index": 0,
                            "delta": delta,
                            "finish_reason": None,
                        }
                        for delta in deltas
                    ],
                },
                {
                    "id": "fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": body["model"],
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": finish_reason}
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                },
            ]
            payload = (
                b"".join(
                    b"data: " + json.dumps(chunk).encode() + b"\n\n" for chunk in chunks
                )
                + b"data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        message: dict[str, object]
        if any(message["role"] == "tool" for message in body["messages"]):
            message = {"role": "assistant", "content": "The result is 42.\n"}
        else:
            name = next(
                tool["function"]["name"]
                for tool in body["tools"]
                if tool["function"]["name"].startswith(server.tool_kind)
            )
            message = {
                "role": "assistant",
                "content": "I will read the configured source.\n",
                "tool_calls": [
                    {
                        "id": "read-source",
                        "function": {
                            "name": name,
                            "arguments": {"query": "SELECT value FROM sample"}
                            if server.tool_kind == "sqlite"
                            else {"query": "fixture"},
                        },
                    }
                ],
            }
        payload = (
            json.dumps(
                {
                    "message": message,
                    "done": True,
                    "prompt_eval_count": 20,
                    "eval_count": 10,
                }
            ).encode()
            + b"\n"
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        """Return Brave-compatible records with source attribution.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        payload = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "Fixture",
                            "description": "The value is 42.",
                            "url": "https://fixture.test/source",
                        }
                    ]
                }
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def server() -> Iterator[ModelServer]:
    """Run a local protocol server for the duration of one test.

    Parameters
    ----------
    None

    Returns
    -------
    Iterator of ModelServer
        Disposable HTTP server.
    """
    server = ModelServer(("127.0.0.1", 0), Handler)
    server.requests = []
    server.tool_kind = "sqlite"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def wait_for(app: QApplication, predicate: Callable[[], bool]) -> None:
    """Pump UI events until an asynchronous operation finishes or times out.

    Parameters
    ----------
    app : QApplication
        Qt event-loop owner.
    predicate : Callable
        Completion condition.

    Returns
    -------
    None
    """
    deadline = time.monotonic() + 15
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate(), "Desktop operation did not finish within 15 seconds."


def configure_desktop(
    window: DesktopWindow,
    app: QApplication,
    endpoint: str,
    source: Path,
    kind: str,
) -> None:
    """Configure persisted models, data connections, and a selected skill.

    Parameters
    ----------
    window : DesktopWindow
        Real desktop under test.
    app : QApplication
        Qt event-loop owner.
    endpoint : str
        Local fixture server URL.
    source : Path
        Read-only source database.
    kind : str
        Data adapter under test.

    Returns
    -------
    None
    """
    wait_for(app, lambda: bool(window.snapshot))
    window.limits.inputs["input_tokens"].setValue(4096)
    window.limits.inputs["output_tokens"].setValue(2048)
    window.limits.save()
    wait_for(app, lambda: window.snapshot["limits"].output_tokens == 2048)
    window.worker.submit(
        "save_connection",
        (
            Connection(
                "local",
                "ollama",
                {
                    "model_id": "fixture",
                    "endpoint": f"{endpoint}/v1",
                    "context_tokens": 8192,
                },
            ),
            "",
        ),
    )
    options: dict[str, JsonValue] = (
        {"database": str(source)} if kind == "sqlite" else {"endpoint": endpoint}
    )
    window.worker.submit(
        "save_connection",
        (
            Connection("data", kind, options),
            "fixture-secret" if kind == "brave" else "",
        ),
    )
    wait_for(app, lambda: len(window.snapshot["connections"]) == 2)
    window.worker.submit("save_skill", Skill("skill", "Fixture", "Answer concisely."))
    wait_for(app, lambda: bool(window.snapshot["skills"]))
    window.skills.items.item(0).setSelected(True)


@pytest.mark.parametrize(
    "kind,approve", [("sqlite", True), ("sqlite", False), ("brave", True)]
)
def test_desktop_real_adapter_approval_and_restart(
    tmp_path: Path,
    server: ModelServer,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    approve: bool,
) -> None:
    """Verify settings, approval, tool execution, history resumption, and deletion.

    Parameters
    ----------
    tmp_path : Path
        Disposable data directory.
    server : ModelServer
        Local model and search protocol fixture.
    qt_app : QApplication
        Headless Qt application.
    monkeypatch : pytest.MonkeyPatch
        Force credential-free OS-backend fallback.
    kind : str
        Real data adapter under test.
    approve : bool
        User decision on the exact proposed action.

    Returns
    -------
    None
    """
    monkeypatch.setattr("amethyst.security.credentials.native_keyring", lambda: None)
    database = tmp_path / "app.sqlite3"
    source = tmp_path / "source.sqlite3"
    with closing(sqlite3.connect(source)) as connection, connection:
        connection.execute("CREATE TABLE sample(value INTEGER)")
        connection.execute("INSERT INTO sample VALUES(42)")
    server.tool_kind = kind
    endpoint = f"http://127.0.0.1:{server.server_port}"
    window = DesktopWindow(DesktopWorker(database))
    try:
        configure_desktop(window, qt_app, endpoint, source, kind)
        window._send("Find the value")
        wait_for(qt_app, lambda: window.approval_dialog is not None)
        dialog = window.approval_dialog
        assert dialog is not None
        review = dialog.findChild(QPlainTextEdit)
        assert review is not None
        assert kind in review.toPlainText()
        dialog.done(
            QDialog.DialogCode.Accepted if approve else QDialog.DialogCode.Rejected
        )
        wait_for(qt_app, lambda: not window.busy)
        wait_for(qt_app, lambda: bool(window.snapshot["conversations"]))
        if approve:
            wait_for(
                qt_app,
                lambda: (
                    "42" in window.snapshot["conversations"][0].messages[-1].content
                ),
            )
        saved = window.snapshot["conversations"][0]
        assert sum(message.role == "user" for message in saved.messages) == 1
        assert len(server.requests) == (2 if approve else 1)
        assert "Answer concisely." in server.requests[0]["messages"][0]["content"]
        if approve:
            assert "42" in saved.messages[-1].content, window.details.toPlainText()
            assert "42" in window.details.toPlainText()
        else:
            assert "denied" in window.details.toPlainText().lower()
        identifier = saved.id
    finally:
        window.close()
        wait_for(qt_app, lambda: window.closed)
    restarted = DesktopWindow(DesktopWorker(database))
    try:
        wait_for(qt_app, lambda: bool(restarted.snapshot))
        restarted._open(identifier)
        wait_for(qt_app, lambda: restarted.conversation_id == identifier)
        assert restarted.snapshot["memory_only"]
        restarted.worker.submit("delete_conversation", identifier)
        wait_for(qt_app, lambda: not restarted.snapshot["conversations"])
        assert b"fixture-secret" not in database.read_bytes()
    finally:
        restarted.close()
        wait_for(qt_app, lambda: restarted.closed)


def test_desktop_budget_cancel_and_close(
    tmp_path: Path,
    server: ModelServer,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep budget, cancellation, and shutdown controls connected to real state.

    Parameters
    ----------
    tmp_path : Path
        Disposable application-data directory.
    server : ModelServer
        Local model protocol fixture.
    qt_app : QApplication
        Qt event-loop owner.
    monkeypatch : pytest.MonkeyPatch
        Force memory-only credentials.

    Returns
    -------
    None
    """
    monkeypatch.setattr("amethyst.security.credentials.native_keyring", lambda: None)
    window = DesktopWindow(DesktopWorker(tmp_path / "app.sqlite3"))
    try:
        configure_desktop(
            window,
            qt_app,
            f"http://127.0.0.1:{server.server_port}",
            tmp_path / "unused.sqlite3",
            "sqlite",
        )
        window.limits.inputs["task_tokens"].setValue(1)
        window.limits.save()
        wait_for(qt_app, lambda: window.snapshot["limits"].task_tokens == 1)
        window._send("Find the value")
        wait_for(qt_app, window.increase.isEnabled)
        assert not server.requests
        window.tokens.setValue(100000)
        window.increase.click()
        wait_for(qt_app, lambda: window.approval_dialog is not None)
        assert window.cancel.isEnabled()
        window.cancel.click()
        wait_for(qt_app, lambda: not window.busy)
        assert "Cancelled" in window.details.toPlainText()
        assert window.approval_dialog is None
        window._new()
        window._send("Another task")
        wait_for(qt_app, window.increase.isEnabled)
    finally:
        window.close()
        wait_for(qt_app, lambda: window.closed)
    restarted = DesktopWindow(DesktopWorker(tmp_path / "app.sqlite3"))
    try:
        wait_for(qt_app, lambda: bool(restarted.snapshot))
        assert restarted.snapshot["limits"].task_tokens == 1
        assert not restarted.snapshot["grants"]
        assert not restarted.snapshot["approvals"]
    finally:
        restarted.close()
        wait_for(qt_app, lambda: restarted.closed)
