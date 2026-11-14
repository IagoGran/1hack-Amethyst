"""Compose the desktop's real application, adapters, and session security."""

import asyncio
import os
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from amethyst.adapters.models.ollama_manager import list_models, pull_model
from amethyst.adapters.persistence import SQLiteRepositories, create_sqlite_repositories
from amethyst.application.connections import ConnectionService
from amethyst.application.resource_monitor import ResourceMonitor, ResourceSnapshot
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
    OperationContext,
)
from amethyst.security.credentials import OSCredentialStore
from amethyst.security.git_metadata import GitBranch, list_branches
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
        self.resource_monitor = ResourceMonitor()
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

    def clear_workspace(self) -> None:
        """Remove the active chat workspace and revoke its read grants.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        for grant in self.agent.permissions.inspect():
            if grant.tool_name == "workspace.read":
                self.agent.permissions.revoke(grant.id)
        self.agent.workspace = None
        self.agent.sandbox = None

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

    async def sample_resources(self) -> ResourceSnapshot:
        """Collect machine telemetry and optional local Ollama attribution.

        Returns
        -------
        ResourceSnapshot
            Best-effort metrics from the machine and configured local daemon.
        """
        connections = await self.repositories.connections.list()
        ollama = next(
            (
                value
                for value in connections
                if value.enabled and value.kind == ConnectionKind.OLLAMA.value
            ),
            None,
        )
        endpoint = None
        if ollama:
            value = ollama.options.get("endpoint")
            endpoint = value if isinstance(value, str) else None
        return await asyncio.to_thread(self.resource_monitor.sample, endpoint)

    async def list_local_ollama_models(self) -> tuple[str, ...]:
        """Query installed models from the configured local Ollama endpoint.

        Returns
        -------
        tuple of str
            Names of locally installed models.
        """
        endpoint = await self._ollama_endpoint()
        return await asyncio.to_thread(list_models, endpoint)

    async def pull_local_ollama_model(
        self, name: str, progress: Callable[[str], None]
    ) -> None:
        """Pull a model through the configured local Ollama service.

        Parameters
        ----------
        name : str
            Model identifier selected by the user.
        progress : Callable or None
            Safe status callback used to update the desktop.

        Returns
        -------
        None
        """
        endpoint = await self._ollama_endpoint()
        await asyncio.to_thread(pull_model, name, endpoint, progress)

    async def _ollama_endpoint(self) -> str | None:
        """Return the first saved local Ollama endpoint, if configured.

        Returns
        -------
        str or None
            Endpoint value or the local service default.
        """
        connections = await self.repositories.connections.list()
        ollama = next(
            (value for value in connections if value.kind == ConnectionKind.OLLAMA.value),
            None,
        )
        if ollama is None:
            return None
        endpoint = ollama.options.get("endpoint")
        return endpoint if isinstance(endpoint, str) else None

    def git_branches(self) -> tuple[GitBranch, ...]:
        """Read branch names only after the active chat grants workspace access.

        Returns
        -------
        tuple of GitBranch
            Bounded local branch metadata without invoking Git commands.

        Raises
        ------
        ContractError
            If the chat has no workspace or its read permission is missing.
        """
        workspace = self.agent.workspace
        if workspace is None:
            raise ContractError(ErrorCode.NOT_FOUND, "Select a chat workspace first.")
        context = OperationContext(uuid4().hex, self.agent.session_id)
        self.agent.permissions.require(
            context, "workspace.read", str(workspace.root)
        )
        return list_branches(workspace.root)

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
