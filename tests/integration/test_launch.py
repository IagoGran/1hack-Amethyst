"""Packaging smoke check for the provisional CLI, not desktop acceptance."""

import subprocess
import sys


def test_module_launch() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "amethyst"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "initial skeleton" in result.stdout
    assert result.stderr == ""
