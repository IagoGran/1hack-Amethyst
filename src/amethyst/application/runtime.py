"""Compose the desktop's real application, adapters, and session security."""

import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from amethyst.adapters.persistence import SQLiteRepositories, create_sqlite_repositories
from amethyst.application.connections import ConnectionService
from amethyst.application.service import AgentService
from amethyst.application.state import ProviderBinding, ToolBinding
from amethyst.application.tools import NamedTool as NamedTool
from amethyst.configuration.catalog import CONNECTION_SPECS, MODEL_KINDS, ConnectionKind
from amethyst.configuration.connections import (
    validate_connection,
)
from amethyst.configuration.limits import Limits
from amethyst.configuration.models import create_pydantic_model
from amethyst.configuration.settings import load_limits, save_limits
from amethyst.configuration.tools import create_tool
from amethyst.domain.contracts import (
    Connection,
    ContractError,
    ErrorCode,
)
from amethyst.security.credentials import OSCredentialStore
from amethyst.security.permissions import ApprovalEngine, PermissionService
from amethyst.security.redaction import Redactor
from amethyst.security.retention import DiagnosticStore
from amethyst.security.sandbox import DockerSandbox, DockerTransport
from amethyst.security.workspace import Workspace


class DesktopRuntime:
    """Own one application session; all methods run on the desktop worker loop."""

    def __init__(
        self,
        repositories: SQLiteRepositories,
        credentials: OSCredentialStore,
        redactor: Redactor,
        *,
        workspace: Path | None = None,
        sandbox_image: str | None = None,
        enable_sandbox: bool = False,
    ) -> None:
        """Compose durable stores and the agent without contacting providers.

        Parameters
        ----------
        repositories : SQLiteRepositories
            Durable conversation, skill, and connection stores.
        credentials : OSCredentialStore
            OS-backed or memory-only secret service.
        redactor : Redactor
            Shared secret filter.
        workspace : Path, optional
            Explicitly selected workspace; no read grant is implied.
        sandbox_image : str, optional
            Pre-provisioned digest-pinned image.
        enable_sandbox : bool
            Explicit assertion that the documented host validation was completed.

        Returns
        -------
        None
        """
        self.repositories = repositories
        self.credentials = credentials
        self.redactor = redactor
        self.connections = ConnectionService(repositories.connections, credentials)
        self.settings_path = repositories.conversations.path.with_suffix(
            ".settings.json"
        )
        session = uuid4().hex
        self.agent = AgentService(
            session_id=session,
            providers={},
            conversations=repositories.conversations,
            skills=repositories.skills,
            approvals=ApprovalEngine(session),
            permissions=PermissionService(session),
            redactor=redactor,
            limits=load_limits(self.settings_path),
        )
        self.agent.diagnostics = DiagnosticStore(
            repositories.conversations.path.parent / "diagnostics", redactor
        )
        self.sandbox_image = sandbox_image
        self.enable_sandbox = enable_sandbox
        self.warnings: list[str] = []
        if workspace is not None:
            self.set_workspace(workspace)

    @classmethod
    async def open(cls, database: Path | None = None, **options) -> "DesktopRuntime":
        """Open local repositories and discover the OS credential backend.

        Parameters
        ----------
        database : Path, optional
            Override the application database location.
        **options : dict
            Explicit workspace and sandbox bootstrap options.

        Returns
        -------
        DesktopRuntime
            Session ready for trusted UI commands.
        """
        redactor = Redactor()
        credentials = await OSCredentialStore.open(redactor)
        return cls(
            create_sqlite_repositories(database), credentials, redactor, **options
        )

    def set_workspace(self, path: Path) -> None:
        """Select a workspace and revoke previous workspace grants.

        Parameters
        ----------
        path : Path
            Existing directory selected by the user.

        Returns
        -------
        None

        Notes
        -----
        Descriptor-relative file access and Docker require Linux or WSL2.
        """
        root = path.resolve(strict=True)
        if not root.is_dir() or os.name != "posix":
            raise ContractError(
                ErrorCode.UNAVAILABLE, "Workspace tools require Linux or WSL2."
            )
        workspace = Workspace(root, self.agent.permissions, self.agent.approvals)
        sandbox = None
        if self.sandbox_image:
            sandbox = DockerSandbox(
                root,
                self.sandbox_image,
                self.agent.approvals,
                DockerTransport(),
                enabled=self.enable_sandbox,
                limits=self.agent.limits,
            )
        for grant in self.agent.permissions.inspect():
            if grant.tool_name == "workspace.read":
                self.agent.permissions.revoke(grant.id)
        self.agent.workspace = workspace
        self.agent.sandbox = sandbox

    async def save_connection(self, connection: Connection, secret: str = "") -> None:
        """Validate settings and store credentials separately from SQLite.

        Parameters
        ----------
        connection : Connection
            Secret-free settings from the trusted form.
        secret : str
            Optional replacement secret; blank preserves the existing reference.

        Returns
        -------
        None
        """
        if secret:
            connection = replace(
                connection, credential_ref=f"connection:{connection.id}"
            )
        validate_connection(connection)
        if secret:
            assert connection.credential_ref is not None
            await self.credentials.set(connection.credential_ref, secret)
        await self.repositories.connections.save(connection)

    async def configure(self, selected: str) -> None:
        """Resolve the chosen model and enabled data tools before a task.

        Parameters
        ----------
        selected : str
            Enabled model connection ID.

        Returns
        -------
        None

        Notes
        -----
        Unavailable optional connectors are reported and omitted for this turn.
        No tool permissions are granted by connection configuration.
        """
        values = await self.connections.list()
        model = next((c for c in values if c.id == selected and c.enabled), None)
        if model is None or model.kind not in MODEL_KINDS:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Select an enabled model connection."
            )
        provider = await create_pydantic_model(model, self.credentials)
        context_tokens = model.options.get("context_tokens")
        if not isinstance(context_tokens, int) or isinstance(context_tokens, bool):
            context_tokens = 32_000
        tools: dict[str, ToolBinding] = {}
        self.warnings = []
        for connection in values:
            if not connection.enabled or connection.kind in MODEL_KINDS:
                continue
            try:
                tool = NamedTool(
                    await create_tool(connection, self.credentials), connection
                )
                kind = CONNECTION_SPECS[ConnectionKind(connection.kind)].result_kind
                tools[tool.definition.name] = ToolBinding(tool, connection.id, kind)
            except ContractError as exc:
                self.warnings.append(
                    f"{connection.id}: {self.redactor.redact(str(exc))}"
                )
        self.agent.providers = {
            selected: ProviderBinding(
                provider,
                str(model.options["model_id"]),
                context_tokens=context_tokens,
            )
        }
        self.agent.tools = tools

    async def close(self) -> None:
        """Cancel tasks, expire grants, and release in-memory credentials.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        await self.agent.close()
        await self.credentials.close()

    def set_limits(self, limits: Limits) -> None:
        """Persist limits and apply them to subsequent tasks and sandbox calls.

        Parameters
        ----------
        limits : Limits
            Validated numeric settings.

        Returns
        -------
        None
        """
        save_limits(self.settings_path, limits)
        self.agent.limits = limits
        if self.agent.sandbox:
            self.agent.sandbox.limits = limits
