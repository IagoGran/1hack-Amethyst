"""Task deadlines, approval wait accounting, and safe retry timing."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

from amethyst.domain.contracts import ContractError, ErrorCode


class Deadline:
    def __init__(
        self, seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Start a monotonic task deadline using an injectable clock.

        Parameters
        ----------
        seconds : float
            Permitted duration in seconds.
        clock : Callable[[], float]
            Clock used to measure time or evaluate retention.

        Returns
        -------
        None
        """
        self.clock = clock
        self.end = clock() + seconds

    def remaining(self) -> float:
        """Return the remaining duration or fail when the deadline has expired.

        Parameters
        ----------
        None

        Returns
        -------
        float
            Measured or permitted duration in seconds.
        """
        remaining = self.end - self.clock()
        if remaining <= 0:
            raise ContractError(ErrorCode.TIMEOUT, "Task deadline exceeded.")
        return remaining

    async def run[T](self, operation: Callable[[], Awaitable[T]], limit: float) -> T:
        """Execute an asynchronous operation within its task and call deadlines.

        Parameters
        ----------
        operation : Callable[[], Awaitable[T]]
            Deferred asynchronous operation to execute.
        limit : float
            Maximum permitted amount for this operation.

        Returns
        -------
        T
            Value produced by the operation.
        """
        try:
            async with asyncio.timeout(min(limit, self.remaining())):
                return await operation()
        except TimeoutError:
            raise ContractError(ErrorCode.TIMEOUT, "Operation timed out.") from None

    async def approval_wait[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        """Suspend task deadline accounting only while awaiting user approval.

        Parameters
        ----------
        operation : Callable[[], Awaitable[T]]
            Deferred asynchronous operation to execute.

        Returns
        -------
        T
            Value produced by the operation.
        """
        self.remaining()
        start = self.clock()
        try:
            return await operation()
        finally:
            self.end += self.clock() - start


def retry_delay(
    error: ContractError, attempt: int, retries: int, *, safe: bool
) -> float | None:
    """Return a bounded retry delay only for transient, safe operations.

    Parameters
    ----------
    error : ContractError
        Boundary failure whose message must remain display-safe.
    attempt : int
        Zero-based index of the current attempt.
    retries : int
        Maximum automatic retries after the initial attempt.
    safe : bool
        Whether retrying is permitted for the current operation.

    Returns
    -------
    float | None
        Value produced by the operation.
    """
    if (
        not safe
        or attempt >= retries
        or not error.transient
        or error.code not in {ErrorCode.UNAVAILABLE, ErrorCode.TIMEOUT}
    ):
        return None
    return float(
        max(2**attempt + random.uniform(0, 0.25), error.retry_after_seconds or 0)
    )
