"""OS Secret Service on Linux/WSL, with an explicit memory-only fallback."""

import asyncio
from typing import Protocol

from amethyst.domain.contracts import ContractError, ErrorCode
from amethyst.security.redaction import Redactor as Redactor
from amethyst.security.redaction import StreamRedactor as StreamRedactor


class NativeKeyring(Protocol):
    def get_password(self, service: str, username: str) -> str | None:
        """Resolve a credential through the explicit OS backend.

        Parameters
        ----------
        service : str
            Application service used by the operation.
        username : str
            Opaque credential account identifier.

        Returns
        -------
        str | None
            Value produced by the operation.
        """
        ...

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store a credential through the explicit OS backend.

        Parameters
        ----------
        service : str
            Application service used by the operation.
        username : str
            Opaque credential account identifier.
        password : str
            Secret credential value kept outside ordinary settings.

        Returns
        -------
        None
        """
        ...

    def delete_password(self, service: str, username: str) -> None:
        """Remove a credential through the explicit OS backend.

        Parameters
        ----------
        service : str
            Application service used by the operation.
        username : str
            Opaque credential account identifier.

        Returns
        -------
        None
        """
        ...


def native_keyring() -> NativeKeyring | None:
    # Do not use keyring's plugin selection: it can select plaintext third parties.
    """Select Linux Secret Service without enabling arbitrary keyring plugins.

    Parameters
    ----------
    None

    Returns
    -------
    NativeKeyring | None
        Value produced by the operation.
    """
    try:
        from keyring.backends.SecretService import Keyring

        backend = Keyring()
        if backend.priority > 0:
            return backend
    except Exception:
        pass
    return None


class OSCredentialStore:
    def __init__(
        self, redactor: Redactor, backend: NativeKeyring | None = None
    ) -> None:
        """Initialize explicit OS storage with an in-memory fallback.

        Parameters
        ----------
        redactor : Redactor
            Credential filter shared by the session.
        backend : NativeKeyring | None
            Explicit OS credential backend, or None for memory-only storage.

        Returns
        -------
        None
        """
        self.redactor = redactor
        self._backend = backend
        self._memory: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def open(cls, redactor: Redactor) -> "OSCredentialStore":
        """Discover the supported credential backend away from the event loop.

        Parameters
        ----------
        redactor : Redactor
            Credential filter shared by the session.

        Returns
        -------
        'OSCredentialStore'
            Value produced by the operation.
        """
        return cls(redactor, await asyncio.to_thread(native_keyring))

    @property
    def memory_only(self) -> bool:
        """Report whether credentials persist only until session exit.

        Parameters
        ----------
        None

        Returns
        -------
        bool
            Whether the stated condition holds.
        """
        return self._backend is None

    def _check(self) -> None:
        """Reject credential access after the session has closed.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        if self._closed:
            raise ContractError(ErrorCode.UNAVAILABLE, "Credential session is closed.")

    async def get(self, reference: str) -> str | None:
        """Resolve a credential and register it with the session redactor.

        Parameters
        ----------
        reference : str
            Opaque credential-store lookup key.

        Returns
        -------
        str | None
            Value produced by the operation.
        """
        async with self._lock:
            self._check()
            if reference in self._memory:
                return self._memory[reference]
            if self._backend is not None:
                try:
                    secret = await asyncio.to_thread(
                        self._backend.get_password, "amethyst", reference
                    )
                    if secret is not None:
                        self.redactor.register(secret)
                        self._memory[reference] = secret
                    return secret
                except Exception:
                    self._backend = None
            return None

    async def set(self, reference: str, secret: str) -> None:
        """Store a credential separately and register it for output redaction.

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
        async with self._lock:
            self._check()
            self.redactor.register(secret)
            self._memory[reference] = secret
            if self._backend is not None:
                try:
                    await asyncio.to_thread(
                        self._backend.set_password, "amethyst", reference, secret
                    )
                except Exception:
                    self._backend = None

    async def delete(self, reference: str) -> None:
        """Delete the credential and report unconfirmed OS-store deletion.

        Parameters
        ----------
        reference : str
            Opaque credential-store lookup key.

        Returns
        -------
        None
        """
        async with self._lock:
            self._check()
            self._memory.pop(reference, None)
            if self._backend is not None:
                try:
                    exists = await asyncio.to_thread(
                        self._backend.get_password, "amethyst", reference
                    )
                    if exists is not None:
                        await asyncio.to_thread(
                            self._backend.delete_password, "amethyst", reference
                        )
                except Exception:
                    self._backend = None
                    raise ContractError(
                        ErrorCode.UNAVAILABLE,
                        "OS credential deletion could not be confirmed.",
                    ) from None

    async def close(self) -> None:
        """Discard in-memory credentials and close the credential session.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        async with self._lock:
            self._memory.clear()
            self._backend = None
            self._closed = True
