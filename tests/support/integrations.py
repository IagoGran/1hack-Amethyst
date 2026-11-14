"""Credential-free vendor client fixtures used by adapter contract tests."""

from types import SimpleNamespace
from typing import Self


class RecordingSQLContext:
    """Share context-manager and statement-recording behavior for driver fixtures."""

    def __init__(self, statements: list[str]) -> None:
        """Bind the fixture to its test-owned SQL statement log.

        Parameters
        ----------
        statements : list of str
            Executed statements in driver order.

        Returns
        -------
        None
        """
        self.statements = statements

    def __enter__(self) -> Self:
        """Return the driver fixture without opening an external connection.

        Parameters
        ----------
        None

        Returns
        -------
        Self
            This fixture.
        """
        return self

    def __exit__(self, *args: object) -> None:
        """Leave the fixture context without suppressing driver errors.

        Parameters
        ----------
        *args : object
            Exception context supplied by the with statement.

        Returns
        -------
        None
        """

    def execute(self, statement: str, params: object = None) -> None:
        """Record a SQL statement without contacting a database.

        Parameters
        ----------
        statement : str
            Submitted statement text.
        params : object
            Bound parameters, unused by this deterministic fixture.

        Returns
        -------
        None
        """
        self.statements.append(statement)


class PostgreSQLCursor(RecordingSQLContext):
    """Return a deterministic single-row SELECT result."""

    description: tuple[SimpleNamespace, ...] | None = None

    def execute(self, statement: str, params: object = None) -> None:
        """Record the statement and expose column metadata for the fixture SELECT.

        Parameters
        ----------
        statement : str
            Submitted statement text.
        params : object
            Bound query parameters.

        Returns
        -------
        None
        """
        super().execute(statement, params)
        if statement == "SELECT 1":
            self.description = (SimpleNamespace(name="value"),)

    def fetchmany(self, limit: int) -> list[tuple[int]]:
        """Return the bounded fixture row.

        Parameters
        ----------
        limit : int
            Requested fetch limit.

        Returns
        -------
        list of tuple
            Deterministic query result.
        """
        return [(1,)][:limit]


class PostgreSQLConnection(RecordingSQLContext):
    """Provide cursors sharing the test's statement log."""

    def cursor(self) -> PostgreSQLCursor:
        """Create a cursor for the same fixture transaction log.

        Parameters
        ----------
        None

        Returns
        -------
        PostgreSQLCursor
            Deterministic cursor fixture.
        """
        return PostgreSQLCursor(self.statements)


class QdrantClient:
    def query_points(self, **kwargs):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        **kwargs : object
            Keyword arguments forwarded to the boundary.

        Returns
        -------
        object
            Value produced by the operation.
        """
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="q1", payload={"text": "match", "url": "https://source.test"}
                )
            ]
        )

    def get_collection(self, collection):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        collection : object
            Configured vector-store collection.

        Returns
        -------
        object
            Value produced by the operation.
        """
        return object()


class ChromaCollection:
    def query(self, **kwargs):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        **kwargs : object
            Keyword arguments forwarded to the boundary.

        Returns
        -------
        object
            Value produced by the operation.
        """
        return {
            "ids": [["c1"]],
            "documents": [["match"]],
            "metadatas": [[{"title": "Source"}]],
        }

    def count(self):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        None

        Returns
        -------
        object
            Value produced by the operation.
        """
        return 1


class ChromaClient:
    def get_collection(self, name):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        name : object
            Field, tool, file, or fixture name.

        Returns
        -------
        object
            Value produced by the operation.
        """
        return ChromaCollection()


class MilvusClient:
    def search(self, **kwargs):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        **kwargs : object
            Keyword arguments forwarded to the boundary.

        Returns
        -------
        object
            Value produced by the operation.
        """
        return [
            [
                {
                    "id": "m1",
                    "entity": {"text": "match", "url": "https://source.test"},
                }
            ]
        ]

    def describe_collection(self, name):
        """Exercise vector adapters preserve source and limit output.

        Parameters
        ----------
        name : object
            Field, tool, file, or fixture name.

        Returns
        -------
        object
            Value produced by the operation.
        """
        return object()
