"""Conservative SQL admission policy in addition to database read-only controls."""

import re

from amethyst.domain.contracts import ContractError, ErrorCode


def require_read_only_sql(query: str) -> None:
    """Conservative admission policy, in addition to C's DB read-only transaction.

    Comments, quoted identifiers and literals are removed before token inspection.
    Unknown/unsafe statements are denied. DB permissions remain mandatory because
    SELECT functions can have side effects and dialects differ.

    Parameters
    ----------
    query : str
        SQL statement to execute through read-only enforcement.

    Returns
    -------
    None
    """
    stripped = re.sub(
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/", " ", query, flags=re.S
    )
    tokens = re.findall(r"[a-z_]+|;", stripped.lower())
    forbidden = {
        "insert",
        "update",
        "delete",
        "merge",
        "replace",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "copy",
        "call",
        "execute",
        "pragma",
        "attach",
        "detach",
        "vacuum",
        "into",
        "lock",
        "load",
        "pg_sleep",
        "dblink",
        "lo_export",
        "lo_import",
    }
    if (
        not tokens
        or tokens[0] not in {"select", "with"}
        or any(t in forbidden for t in tokens)
        or ";" in tokens[:-1]
        or "$" in stripped
    ):
        raise ContractError(
            ErrorCode.PERMISSION_DENIED, "Only read-only SQL queries are permitted."
        )
