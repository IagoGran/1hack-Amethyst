"""Shared approval storage; policy and consumption remain in concrete services."""

from amethyst.domain.contracts import Approval, ContractError, ErrorCode


class ApprovalStore:
    """Own approval records and their common safe lookup behavior."""

    def __init__(self) -> None:
        """Initialize session-local approval records.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._approvals: dict[str, Approval] = {}

    async def inspect(self, approval_id: str) -> Approval:
        """Look up an approval without changing its authorization state.

        Parameters
        ----------
        approval_id : str
            Stable approval identifier.

        Returns
        -------
        Approval
            Current approval record.
        """
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ContractError(ErrorCode.NOT_FOUND, "Approval not found.") from None
