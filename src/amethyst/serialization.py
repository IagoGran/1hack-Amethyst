"""Bound JSON record sequences without repeatedly encoding retained records."""

import json
from collections.abc import Iterable


def bounded_json_records(
    records: Iterable[object], limit: int, *, prefix: str = "[", suffix: str = "]"
) -> tuple[str, int]:
    """Encode the largest record prefix that fits a UTF-8 byte budget.

    Parameters
    ----------
    records : iterable of object
        JSON-compatible records; unsupported scalar values are converted to text.
    limit : int
        Maximum output size in bytes, including the envelope and separators.
    prefix, suffix : str
        JSON envelope surrounding the comma-separated records.

    Returns
    -------
    tuple of str and int
        Serialized payload and number of retained records.

    Raises
    ------
    ValueError
        If the empty envelope alone exceeds the byte limit.

    Notes
    -----
    Each examined record is serialized once. Records are never partially retained.
    Callers retain responsibility for row/chunk policies and matching sources.
    """
    used = len(prefix.encode("utf-8")) + len(suffix.encode("utf-8"))
    if used > limit:
        raise ValueError("JSON metadata exceeds the output limit.")
    encoded: list[str] = []
    for record in records:
        item = json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), default=str
        )
        size = len(item.encode("utf-8")) + bool(encoded)
        if used + size > limit:
            break
        encoded.append(item)
        used += size
    return prefix + ",".join(encoded) + suffix, len(encoded)
