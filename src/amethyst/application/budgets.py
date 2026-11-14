"""Conservative token estimates and cumulative task budget accounting."""

import json
from dataclasses import asdict

from amethyst.domain.contracts import ContractError, ErrorCode, ModelRequest, Usage


def token_bound(text: str) -> int:
    """UTF-8 byte upper bound; conservative until C supplies model tokenizers.

    Parameters
    ----------
    text : str
        Text fragment to inspect, redact, or display.

    Returns
    -------
    int
        Computed count or amount.
    """
    return len(text.encode("utf-8"))


def request_tokens(request: ModelRequest) -> int:
    """Estimate request input using a conservative UTF-8 byte upper bound.

    Parameters
    ----------
    request : ModelRequest
        Typed request describing the operation and its scope.

    Returns
    -------
    int
        Computed count or amount.
    """
    return (
        token_bound(
            json.dumps(
                {
                    "messages": [asdict(m) for m in request.messages],
                    "tools": [asdict(t) for t in request.tools],
                },
                ensure_ascii=False,
            )
        )
        + 128
    )


class TokenBudget:
    def __init__(self, limit: int) -> None:
        """Initialize cumulative token accounting for one task.

        Parameters
        ----------
        limit : int
            Maximum permitted amount for this operation.

        Returns
        -------
        None
        """
        self.limit = limit
        self.used = 0

    def can_reserve(self, tokens: int) -> bool:
        """Check whether the next request fits the remaining token budget.

        Parameters
        ----------
        tokens : int
            Requested token reservation or positive budget increase.

        Returns
        -------
        bool
            Whether the stated condition holds.
        """
        return self.used + tokens <= self.limit

    def charge(self, usage: Usage | None, reserved: int) -> Usage:
        """Charge observed usage or the conservative unknown-usage reservation.

        Parameters
        ----------
        usage : Usage | None
            Observed provider usage, or None when unknown.
        reserved : int
            Conservative token reservation used when actual usage is unknown.

        Returns
        -------
        Usage
            Value produced by the operation.
        """
        if usage is None:
            usage = Usage(reserved, 0)
        if usage.input_tokens < 0 or usage.output_tokens < 0:
            self.used += reserved
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Provider returned invalid usage."
            )
        self.used += usage.input_tokens + usage.output_tokens
        return usage

    def increase(self, tokens: int) -> None:
        """Apply an explicitly requested positive token budget increase.

        Parameters
        ----------
        tokens : int
            Requested token reservation or positive budget increase.

        Returns
        -------
        None
        """
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Budget increase must be a positive integer."
            )
        self.limit += tokens
