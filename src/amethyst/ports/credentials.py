"""Opaque credential lookup for adapter construction; no export operation."""

from typing import Protocol


class CredentialStore(Protocol):
    async def get(self, reference: str) -> str | None:
        """Look up a credential using an opaque reference.

        Parameters
        ----------
        reference : str
            Opaque credential-store lookup key.

        Returns
        -------
        str | None
            Value produced by the operation.
        """
        ...

    async def set(self, reference: str, secret: str) -> None:
        """Store credential material behind an opaque reference.

        Parameters
        ----------
        reference : str
            Opaque credential-store lookup key.
        secret : str
            Credential material kept separate from public configuration.

        Returns
        -------
        None
        """
        ...

    async def delete(self, reference: str) -> None:
        """Delete the selected stored record idempotently.

        Parameters
        ----------
        reference : str
            Opaque credential-store lookup key.

        Returns
        -------
        None
        """
        ...
