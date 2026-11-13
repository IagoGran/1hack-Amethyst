"""OS Secret Service on Linux/WSL, with an explicit memory-only fallback."""

import asyncio
import re
from typing import Protocol

from amethyst.domain.contracts import ContractError, ErrorCode


class Redactor:
    def __init__(self) -> None:
        self._secrets: set[str] = set()

    def register(self, value: str) -> None:
        if value:
            self._secrets.add(value)

    def redact(self, text: str) -> str:
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[REDACTED]", text)
        text = re.sub(
            r"(?i)((?:api[_-]?key|password|secret|token)\s*[:=]\s*)[^\s,;]+",
            r"\1[REDACTED]",
            text,
        )
        text = re.sub(r"(://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)
        return text


class StreamRedactor:
    """Release complete lines while retaining possible cross-chunk secrets."""

    def __init__(self, redactor: Redactor) -> None:
        self.redactor = redactor
        self.pending = ""

    def feed(self, text: str) -> str:
        self.pending += text
        reserve = max((len(s) for s in self.redactor._secrets), default=0)
        cut = self.pending.rfind("\n", 0, max(0, len(self.pending) - reserve)) + 1
        for secret in self.redactor._secrets:
            start = self.pending.find(secret)
            if 0 <= start < cut < start + len(secret):
                cut = start
        ready, self.pending = self.pending[:cut], self.pending[cut:]
        return self.redactor.redact(ready)

    def finish(self) -> str:
        ready, self.pending = self.pending, ""
        return self.redactor.redact(ready)


class NativeKeyring(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


def native_keyring() -> NativeKeyring | None:
    # Do not use keyring's plugin selection: it can select plaintext third parties.
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
        self.redactor = redactor
        self._backend = backend
        self._memory: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def open(cls, redactor: Redactor) -> "OSCredentialStore":
        return cls(redactor, await asyncio.to_thread(native_keyring))

    @property
    def memory_only(self) -> bool:
        return self._backend is None

    def _check(self) -> None:
        if self._closed:
            raise ContractError(ErrorCode.UNAVAILABLE, "Credential session is closed.")

    async def get(self, reference: str) -> str | None:
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
        async with self._lock:
            self._memory.clear()
            self._backend = None
            self._closed = True
