"""Credential and streaming text redaction independent of credential storage."""

import re


class Redactor:
    def __init__(self) -> None:
        """Initialize known-secret tracking for the session.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        self._secrets: set[str] = set()
        self.secrets: tuple[str, ...] = ()
        self.max_secret_length = 0

    def register(self, value: str) -> None:
        """Register a secret and refresh the cached longest-first ordering.

        Parameters
        ----------
        value : str
            Value supplied to the operation.

        Returns
        -------
        None
        """
        if value and value not in self._secrets:
            self._secrets.add(value)
            self.secrets = tuple(sorted(self._secrets, key=len, reverse=True))
            self.max_secret_length = len(self.secrets[0])

    def redact(self, text: str) -> str:
        """Remove known credentials and common inline-secret patterns.

        Parameters
        ----------
        text : str
            Text fragment to inspect, redact, or display.

        Returns
        -------
        str
            Text produced by the operation.
        """
        for secret in self.secrets:
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
        """Bind a redactor and retain potentially incomplete secret fragments.

        Parameters
        ----------
        redactor : Redactor
            Credential filter shared by the session.

        Returns
        -------
        None
        """
        self.redactor = redactor
        self.pending = ""

    def feed(self, text: str) -> str:
        """Release complete safe lines while retaining cross-fragment secrets.

        Parameters
        ----------
        text : str
            Text fragment to inspect, redact, or display.

        Returns
        -------
        str
            Text produced by the operation.
        """
        self.pending += text
        reserve = self.redactor.max_secret_length
        cut = self.pending.rfind("\n", 0, max(0, len(self.pending) - reserve)) + 1
        for secret in self.redactor.secrets:
            start = self.pending.find(secret)
            if 0 <= start < cut < start + len(secret):
                cut = start
        ready, self.pending = self.pending[:cut], self.pending[cut:]
        return self.redactor.redact(ready)

    def finish(self) -> str:
        """Redact and release the final retained stream fragment.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Text produced by the operation.
        """
        ready, self.pending = self.pending, ""
        return self.redactor.redact(ready)
