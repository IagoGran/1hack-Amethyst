"""Deterministic tests for local telemetry, Ollama, and Git metadata helpers."""

from pathlib import Path

import pytest

from amethyst.adapters.models.ollama_manager import _local_endpoint
from amethyst.application.resource_monitor import ResourceMonitor
from amethyst.domain.contracts import ContractError
from amethyst.security.git_metadata import list_branches


def test_local_ollama_endpoint_rejects_remote_hosts() -> None:
    """Model management cannot be directed to an external service.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    with pytest.raises(ContractError):
        _local_endpoint("http://models.example:11434")
    assert _local_endpoint("http://localhost:11434") == "http://localhost:11434"


def test_git_branch_listing_reads_only_local_refs(tmp_path: Path) -> None:
    """The Git metadata reader reports current and packed branch tips.

    Parameters
    ----------
    tmp_path : Path
        Isolated temporary directory supplied by pytest.

    Returns
    -------
    None
    """
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="ascii")
    (git / "refs" / "heads" / "main").write_text("a" * 40, encoding="ascii")
    (git / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled\n" + "b" * 40 + " refs/heads/dev\n",
        encoding="ascii",
    )

    branches = list_branches(tmp_path)

    assert [(item.name, item.commit, item.current) for item in branches] == [
        ("refs/heads/main", "aaaaaaa", True),
        ("refs/heads/dev", "bbbbbbb", False),
    ]


def test_resource_monitor_reports_supported_percentages_or_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry values preserve unsupported states without host dependencies.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Replace machine telemetry sources with deterministic values.

    Returns
    -------
    None
    """
    monitor = ResourceMonitor()
    monkeypatch.setattr(monitor, "_cpu_percent", lambda: 75.0)
    monkeypatch.setattr(monitor, "_memory_percent", lambda: None)
    monkeypatch.setattr(monitor, "_gpu_percentages", lambda: (None, None))
    monkeypatch.setattr(monitor, "_ollama_usage", lambda _endpoint: ((), None))
    snapshot = monitor.sample()

    assert snapshot.cpu_percent == 75.0
    assert snapshot.memory_percent is None
    assert snapshot.gpu_percent is None
    assert snapshot.gpu_memory_percent is None
    assert snapshot.ollama_models == ()
