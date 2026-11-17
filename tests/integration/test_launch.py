"""Packaging smoke check independent of a display server or live services."""

import subprocess
import sys


def test_module_launch() -> None:
    """Check the installed entry point without starting a GUI event loop.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    result = subprocess.run(
        [sys.executable, "-m", "amethyst", "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "1hack-amethyst 0.1.0" in result.stdout
    assert result.stderr == ""
