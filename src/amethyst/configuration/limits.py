"""Approved defaults; application and adapters share this immutable policy."""

from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class Limits:
    tool_seconds: float = 30
    model_idle_seconds: float = 60
    model_total_seconds: float = 300
    command_seconds: float = 120
    task_seconds: float = 600
    task_tokens: int = 100_000
    input_tokens: int = 32_000
    output_tokens: int = 8_000
    retrieval_chunks: int = 8
    chunk_tokens: int = 1_000
    sql_rows: int = 1_000
    output_bytes: int = 1_048_576
    retries: int = 2

    def __post_init__(self) -> None:
        """Validate positive finite limits and the approved retry ceiling.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        import math

        for field in fields(self):
            value = getattr(self, field.name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or (field.type is int and not isinstance(value, int))
                or not math.isfinite(value)
                or (value < 0 if field.name == "retries" else value <= 0)
            ):
                raise ValueError(f"{field.name} must be finite and positive.")
        if self.retries > 2:
            raise ValueError("At most two automatic retries are allowed.")
