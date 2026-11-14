"""Local repositories: save is upsert, missing load raises NOT_FOUND.

Delete is idempotent; list order is by ID. Values are detached snapshots.
Durable implementations retain values until explicit deletion, across restarts.
"""

from typing import Protocol

from amethyst.domain.contracts import Connection, Conversation, Skill


class Identified(Protocol):
    """A record with a stable repository identifier."""

    @property
    def id(self) -> str:
        """Return the stable record identifier.

        Parameters
        ----------
        None

        Returns
        -------
        str
            Persistent identity.
        """
        ...


class Repository[T](Protocol):
    """Upsert, load, list, and delete detached record snapshots."""

    async def save(self, value: T) -> None:
        """Persist a detached snapshot, replacing a record with the same ID.

        Parameters
        ----------
        value : T
            Domain record to persist.

        Returns
        -------
        None
        """
        ...

    async def load(self, item_id: str) -> T:
        """Load a detached snapshot or raise NOT_FOUND.

        Parameters
        ----------
        item_id : str
            Persistent identifier.

        Returns
        -------
        T
            Detached domain record.
        """
        ...

    async def list(self) -> tuple[T, ...]:
        """List detached records ordered by persistent identifier.

        Parameters
        ----------
        None

        Returns
        -------
        tuple of T
            Stable ordered snapshots.
        """
        ...

    async def delete(self, item_id: str) -> None:
        """Delete a record idempotently.

        Parameters
        ----------
        item_id : str
            Persistent identifier.

        Returns
        -------
        None
        """
        ...


class ConversationRepository(Repository[Conversation], Protocol):
    """Conversation history storage boundary."""


class SkillRepository(Repository[Skill], Protocol):
    """Reusable skill storage boundary."""


class ConnectionRepository(Repository[Connection], Protocol):
    """Secret-free connection storage boundary."""
