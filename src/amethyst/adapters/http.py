"""Small HTTP response helpers shared by model and search adapters."""


def retry_after(value: str | None) -> float | None:
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
