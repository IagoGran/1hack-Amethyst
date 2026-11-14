"""Persist numeric operational settings separately from credentials."""

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from amethyst.configuration.limits import Limits


def load_limits(path: Path) -> Limits:
    """Read validated operational limits or use defaults for a new installation.

    Parameters
    ----------
    path : Path
        Application-owned settings file.

    Returns
    -------
    Limits
        Validated numeric limits.

    Notes
    -----
    Invalid existing settings raise an error instead of silently changing policy.
    """
    if not path.exists():
        return Limits()
    return Limits(**json.loads(path.read_text(encoding="utf-8")))


def save_limits(path: Path, limits: Limits) -> None:
    """Atomically save validated numeric settings without credential material.

    Parameters
    ----------
    path : Path
        Application-owned settings file.
    limits : Limits
        Validated limits to persist.

    Returns
    -------
    None
    """
    temporary = path.with_name(f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(asdict(limits)), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
