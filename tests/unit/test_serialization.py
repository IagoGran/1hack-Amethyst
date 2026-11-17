"""Behavioral checks for bounded Unicode results and matching retrieval sources."""

import json

import pytest

from amethyst.adapters.tools.web_search import BraveSearchTool
from amethyst.serialization import bounded_json_records


@pytest.mark.parametrize("limit", [2, 15, 40, 1000])
def test_record_bounds_preserve_unicode_and_complete_records(limit: int) -> None:
    """Retain an ordered prefix of whole records within the UTF-8 byte budget.

    Parameters
    ----------
    limit : int
        Maximum serialized output size.

    Returns
    -------
    None
    """
    records = [{"text": "é"}, {"text": "🟣"}, {"text": "third"}]
    content, retained = bounded_json_records(records, limit)
    assert len(content.encode("utf-8")) <= limit
    assert json.loads(content) == records[:retained]
    if retained < len(records):
        next_prefix = json.dumps(
            records[: retained + 1], ensure_ascii=False, separators=(",", ":")
        )
        assert len(next_prefix.encode("utf-8")) > limit


def test_metadata_envelope_is_included_in_byte_limit() -> None:
    """Account for SQL columns and the result envelope before retaining rows.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    prefix = '{"columns":["é"],"rows":['
    empty_size = len((prefix + "]}").encode("utf-8"))
    content, retained = bounded_json_records(
        [{"é": "value"}], empty_size, prefix=prefix, suffix="]}"
    )
    assert json.loads(content) == {"columns": ["é"], "rows": []}
    assert retained == 0
    with pytest.raises(ValueError):
        bounded_json_records([], empty_size - 1, prefix=prefix, suffix="]}")


def test_search_output_preserves_bounds_and_source_alignment() -> None:
    """Keep source metadata aligned with the exact JSON records retained.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    results = [
        {"url": f"https://fixture.test/{index}", "title": "é", "description": "🟣"}
        for index in range(3)
    ]
    tool = BraveSearchTool("fixture")
    result = tool._result({"web": {"results": results}}, "call", 3, 100)
    retained = json.loads(result.content)
    assert len(result.content.encode("utf-8")) <= 100
    assert len(retained) == len(result.sources) == 1
    assert result.sources[0].url == retained[0]["url"]
    assert result.truncated
