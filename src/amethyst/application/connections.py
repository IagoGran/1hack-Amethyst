"""Application-facing CRUD and health checks for configured connectors."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from amethyst.configuration.connections import (
    ConnectionKind,
    create_model_provider,
    create_tool,
    validate_connection,
)
from amethyst.domain.contracts import (
    Connection,
    ConnectionHealth,
    ContractError,
    ErrorCode,
    OperationContext,
)
from amethyst.ports.credentials import CredentialStore
from amethyst.ports.persistence import ConnectionRepository


class ConnectionService:
    def __init__(
        self, repository: ConnectionRepository, credentials: CredentialStore
    ) -> None:
        """Create a service over connector persistence and credentials.

        Parameters
        ----------
        repository : ConnectionRepository
            Persistent connector settings.
        credentials : CredentialStore
            Secure credential lookup service.
        """
        self._repository = repository
        self._credentials = credentials

    async def list(self) -> tuple[Connection, ...]:
        """List configured connections without resolving their secrets.

        Returns
        -------
        tuple of Connection
            Stored connector settings.
        """
        return await self._repository.list()

    async def add(self, connection: Connection) -> Connection:
        """Validate and persist a connection with a unique ID.

        Parameters
        ----------
        connection : Connection
            Connector settings to create.

        Returns
        -------
        Connection
            Saved validated settings.

        Raises
        ------
        ContractError
            If settings are invalid or the ID already exists.
        """
        connection = validate_connection(connection)
        try:
            await self._repository.load(connection.id)
        except ContractError as exc:
            if exc.code != ErrorCode.NOT_FOUND:
                raise
        else:
            raise ContractError(ErrorCode.CONFLICT, "Connection ID already exists.")
        await self._repository.save(connection)
        return connection

    async def update(self, connection: Connection) -> Connection:
        """Validate and replace an existing connection.

        Parameters
        ----------
        connection : Connection
            Replacement connector settings.

        Returns
        -------
        Connection
            Saved validated settings.

        Raises
        ------
        ContractError
            If settings are invalid or the connection does not exist.
        """
        connection = validate_connection(connection)
        try:
            await self._repository.load(connection.id)
        except ContractError as exc:
            if exc.code == ErrorCode.NOT_FOUND:
                raise
            raise
        await self._repository.save(connection)
        return connection

    async def set_enabled(self, connection_id: str, enabled: bool) -> Connection:
        """Change a connection's enabled flag without changing its settings.

        Parameters
        ----------
        connection_id : str
            Stored connection identifier.
        enabled : bool
            Whether the connection should be enabled.

        Returns
        -------
        Connection
            Updated connection settings.
        """
        current = await self._repository.load(connection_id)
        updated = Connection(
            current.id,
            current.kind,
            current.options.copy(),
            enabled,
            current.credential_ref,
        )
        await self._repository.save(updated)
        return updated

    async def delete(self, connection_id: str) -> None:
        """Delete a configured connection.

        Parameters
        ----------
        connection_id : str
            Stored connection identifier.

        Raises
        ------
        ContractError
            If the connection does not exist.
        """
        connection = await self._repository.load(connection_id)
        await self._repository.delete(connection.id)

    async def test(
        self, connection_id: str, context: OperationContext
    ) -> ConnectionHealth:
        """Check connector availability without returning secret material.

        Parameters
        ----------
        connection_id : str
            Stored connection identifier.
        context : OperationContext
            Timeout and operation scope.

        Returns
        -------
        ConnectionHealth
            Redacted health result or an unsupported/disabled error.
        """
        connection = await self._repository.load(connection_id)
        if not connection.enabled:
            return ConnectionHealth(
                False, "Connection is disabled.", ErrorCode.PERMISSION_DENIED
            )
        try:
            if ConnectionKind(connection.kind) in {
                ConnectionKind.OPENAI,
                ConnectionKind.GEMINI,
                ConnectionKind.DEEPSEEK,
                ConnectionKind.OLLAMA,
            }:
                tool = await create_model_provider(connection, self._credentials)
            else:
                tool = await create_tool(connection, self._credentials)
        except ContractError as exc:
            return ConnectionHealth(False, str(exc), exc.code)
        tester = getattr(tool, "test_connection", None)
        if tester is None:
            return ConnectionHealth(
                False, "Connection cannot be tested.", ErrorCode.UNAVAILABLE
            )
        test_function = cast(
            Callable[[OperationContext], Awaitable[ConnectionHealth]], tester
        )
        return await test_function(context)
