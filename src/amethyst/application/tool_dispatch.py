"""Prepare and authorize workspace, sandbox, and configured tool operations."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import asdict, replace
from functools import partial
from typing import TYPE_CHECKING
from uuid import uuid4

from amethyst.application.limits import bounded_result
from amethyst.application.state import PreparedOperation, RunningTask, ToolBinding
from amethyst.application.timing import retry_delay
from amethyst.domain.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    ContractError,
    ErrorCode,
    OperationContext,
    ProposedAction,
    SandboxRequest,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.security.permissions import fingerprint
from amethyst.security.sql import require_read_only_sql

if TYPE_CHECKING:
    from amethyst.application.service import AgentService


class ToolDispatcher:
    """Keep tool execution and approval rules independent of model generation."""

    def __init__(self, agent: AgentService) -> None:
        """Bind the task orchestrator's security services and operation limits.

        Parameters
        ----------
        agent : AgentService
            Session owner; trusted controls remain on the orchestrator.

        Returns
        -------
        None
        """
        self.agent = agent

    def definitions(self) -> tuple[ToolDefinition, ...]:
        """Describe enabled connectors and configured workspace/container tools.

        Parameters
        ----------
        None

        Returns
        -------
        tuple[ToolDefinition, ...]
            Value produced by the operation.
        """
        definitions = [
            binding.tool.definition
            for binding in self.agent.tools.values()
            if binding.enabled
        ]
        if self.agent.workspace:
            definitions.extend(
                (
                    ToolDefinition(
                        "workspace.read",
                        "Read an explicitly permitted UTF-8 file.",
                        {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                            "required": ["path"],
                        },
                    ),
                    ToolDefinition(
                        "workspace.edit",
                        "Propose a reviewed file change; null content deletes.",
                        {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": ["string", "null"]},
                            },
                            "required": ["path", "content"],
                        },
                        read_only=False,
                    ),
                )
            )
        if self.agent.sandbox:
            definitions.append(
                ToolDefinition(
                    "sandbox.run",
                    "Run an approved command in a read-only container workspace.",
                    {
                        "type": "object",
                        "properties": {
                            "argv": {"type": "array", "items": {"type": "string"}},
                            "working_directory": {"type": "string"},
                            "network_enabled": {"type": "boolean"},
                        },
                        "required": ["argv"],
                    },
                    read_only=False,
                )
            )
        return tuple(definitions)

    async def execute(self, record: RunningTask, call: ToolCall) -> ToolResult:
        """Review protected actions before execution and redact returned data.

        Parameters
        ----------
        record : RunningTask
            Task-local or persisted record owned by the operation.
        call : ToolCall
            Tool invocation with its identifier, name, and arguments.

        Returns
        -------
        ToolResult
            Bounded result with call identity and source metadata.
        """
        call = deepcopy(call)
        operation = self.prepare(record, call)
        approval_id: str | None = None
        if operation.action is not None:
            if any(
                self.agent.redactor.redact(change.diff) != change.diff
                for change in operation.action.changes
            ):
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED,
                    "Proposed diff contains protected credentials.",
                )
            proposal = ApprovalRequest(
                uuid4().hex, record.task.id, self.agent.session_id, (operation.action,)
            )
            await self.agent.approvals.request(proposal)
            await self.agent._state(
                record,
                TaskStatus.AWAITING_APPROVAL,
                "Waiting for review of the listed action.",
            )
            await self.agent._emit(record, proposal)
            decision = await record.deadline.approval_wait(
                lambda: self.agent.approvals.wait(proposal.id)
            )
            if decision.status != ApprovalStatus.GRANTED:
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED,
                    "Action approval was denied or revoked.",
                )
            approval_id = proposal.id
            await self.agent._state(
                record, TaskStatus.RUNNING, "Executing the approved action."
            )
        timeout = (
            self.agent.limits.command_seconds
            if call.name == "sandbox.run"
            else self.agent.limits.tool_seconds
        )
        context = self.agent._context(record, timeout)
        result = await record.deadline.run(
            lambda: operation.execute(approval_id, context), timeout
        )
        if result.call_id != call.id:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Tool returned an unrelated call ID."
            )
        return replace(
            result,
            content=self.agent.redactor.redact(result.content),
            sources=tuple(
                replace(
                    s,
                    identifier=self.agent.redactor.redact(s.identifier),
                    title=self.agent.redactor.redact(s.title),
                    url=self.agent.redactor.redact(s.url) if s.url else None,
                )
                for s in result.sources
            ),
        )

    def prepare(self, record: RunningTask, call: ToolCall) -> PreparedOperation:
        """Select the operation builder without invoking protected actions.

        Parameters
        ----------
        record : RunningTask
            Task-local state and deadline.
        call : ToolCall
            Agent-selected operation.

        Returns
        -------
        PreparedOperation
            Exact proposal and its deferred execution function.
        """
        if call.name == "workspace.read" and self.agent.workspace is not None:
            return self._prepare_read(record, call)
        if call.name == "workspace.edit" and self.agent.workspace is not None:
            return self._prepare_edit(record, call)
        if call.name == "sandbox.run" and self.agent.sandbox is not None:
            return self._prepare_command(record, call)
        return self._prepare_connector(record, call)

    def _prepare_read(self, record: RunningTask, call: ToolCall) -> PreparedOperation:
        """Prepare a permission-checked workspace read.

        Parameters
        ----------
        record : RunningTask
            Task context and operation limits.
        call : ToolCall
            Requested tool name and arguments.

        Returns
        -------
        PreparedOperation
            Optional action approval and deferred execution.
        """
        workspace = self.agent.workspace
        assert workspace is not None
        path = self._string(call, "path")

        async def read(
            approval_id: str | None, context: OperationContext
        ) -> ToolResult:
            """Read the scoped file through workspace permission checks.

            Parameters
            ----------
            approval_id : str or None
                Exact-action approval identifier when required.
            context : OperationContext
                Task/session scope and operation limits.

            Returns
            -------
            ToolResult
                Authorized operation result.
            """
            return bounded_result(
                ToolResult(call.id, workspace.read(path, context)), self.agent.limits
            )

        return PreparedOperation(None, read)

    def _prepare_edit(self, record: RunningTask, call: ToolCall) -> PreparedOperation:
        """Bind a workspace mutation to the exact reviewed diff.

        Parameters
        ----------
        record : RunningTask
            Task context and operation limits.
        call : ToolCall
            Requested tool name and arguments.

        Returns
        -------
        PreparedOperation
            Optional action approval and deferred execution.
        """
        workspace = self.agent.workspace
        assert workspace is not None
        path = self._string(call, "path")
        if "content" not in call.arguments or not isinstance(
            call.arguments["content"], str | type(None)
        ):
            raise ContractError(
                ErrorCode.INVALID_INPUT, "File content must be text or null."
            )
        edit = workspace.propose(
            path,
            call.arguments["content"],
            self.agent._context(record, self.agent.limits.tool_seconds),
        )

        async def apply(
            approval_id: str | None, context: OperationContext
        ) -> ToolResult:
            """Apply the exact workspace diff after consuming its approval.

            Parameters
            ----------
            approval_id : str or None
                Exact-action approval identifier when required.
            context : OperationContext
                Task/session scope and operation limits.

            Returns
            -------
            ToolResult
                Authorized operation result.
            """
            assert approval_id is not None
            await workspace.apply(edit, approval_id, context)
            return ToolResult(call.id, "Reviewed file change applied.")

        return PreparedOperation(edit.action, apply)

    def _prepare_command(
        self, record: RunningTask, call: ToolCall
    ) -> PreparedOperation:
        """Bind sandbox execution to its exact command proposal.

        Parameters
        ----------
        record : RunningTask
            Task context and operation limits.
        call : ToolCall
            Requested tool name and arguments.

        Returns
        -------
        PreparedOperation
            Optional action approval and deferred execution.
        """
        sandbox = self.agent.sandbox
        assert sandbox is not None
        argv = call.arguments.get("argv")
        network = call.arguments.get("network_enabled", False)
        if (
            not isinstance(argv, list)
            or not all(isinstance(a, str) for a in argv)
            or not isinstance(network, bool)
        ):
            raise ContractError(ErrorCode.INVALID_INPUT, "Invalid command arguments.")
        request = SandboxRequest(
            call.id,
            "",
            "",
            sandbox.workspace,
            tuple(str(a) for a in argv),
            self._string(call, "working_directory", "."),
            network,
            self.agent.limits.command_seconds,
            self.agent.limits.output_bytes,
        )
        action = sandbox.proposal(request)

        async def run(approval_id: str | None, context: OperationContext) -> ToolResult:
            """Run the exact approved container request and validate its outcome.

            Parameters
            ----------
            approval_id : str or None
                Exact-action approval identifier when required.
            context : OperationContext
                Task/session scope and operation limits.

            Returns
            -------
            ToolResult
                Authorized operation result.
            """
            assert approval_id is not None
            result = await sandbox.run(
                replace(
                    request, approval_id=approval_id, fingerprint=action.fingerprint
                ),
                context,
            )
            if result.outcome != "completed":
                code = (
                    ErrorCode.TIMEOUT
                    if result.outcome == "timeout"
                    else ErrorCode.OUTCOME_UNKNOWN
                )
                raise ContractError(code, "Sandbox command did not complete.")
            return bounded_result(
                ToolResult(
                    call.id, json.dumps(asdict(result)), truncated=result.truncated
                ),
                self.agent.limits,
            )

        return PreparedOperation(action, run)

    def _prepare_connector(
        self, record: RunningTask, call: ToolCall
    ) -> PreparedOperation:
        """Prepare a configured connector with grant and retry checks.

        Parameters
        ----------
        record : RunningTask
            Task context and operation limits.
        call : ToolCall
            Requested tool name and arguments.

        Returns
        -------
        PreparedOperation
            Optional action approval and deferred execution.
        """
        binding = self.agent.tools.get(call.name)
        if binding is None or not binding.enabled:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Tool is unavailable or disabled."
            )
        if binding.kind == "sql":
            require_read_only_sql(self._string(call, "query"))
        context = self.agent._context(record, self.agent.limits.tool_seconds)
        definition = binding.tool.definition
        session_granted = False
        if definition.read_only:
            try:
                self.agent.permissions.require(context, call.name, binding.resource)
                session_granted = True
            except ContractError:
                pass
        action = ProposedAction(
            call.id,
            call.name,
            f"Invoke {call.name} with {json.dumps(call.arguments, sort_keys=True)}",
            (binding.resource,),
            fingerprint({"call": asdict(call), "resource": binding.resource}),
            high_impact=not binding.tool.definition.read_only,
        )

        invoke = partial(
            self._invoke_connector, binding, call, definition, session_granted, action
        )
        return PreparedOperation(None if session_granted else action, invoke)

    async def _invoke_connector(
        self,
        binding: ToolBinding,
        call: ToolCall,
        definition: ToolDefinition,
        session_granted: bool,
        action: ProposedAction,
        approval_id: str | None,
        context: OperationContext,
    ) -> ToolResult:
        """Recheck authorization before each safe connector attempt.

        Parameters
        ----------
        binding : ToolBinding
            Captured tool configuration and resource.
        call : ToolCall
            Exact requested invocation.
        definition : ToolDefinition
            Tool schema at proposal time.
        session_granted : bool
            Whether a read-only session grant authorized this operation.
        action : ProposedAction
            Exact proposal bound to connector arguments and resource.
        approval_id : str or None
            Explicit approval identifier when a session grant was unavailable.
        context : OperationContext
            Task/session scope and call limits.

        Returns
        -------
        ToolResult
            Bounded connector output after authorization checks.
        """
        if approval_id is not None:
            await self.agent.approvals.consume(
                approval_id, call.id, action.fingerprint, context
            )
        for attempt in range(self.agent.limits.retries + 1):
            if session_granted:
                self.agent.permissions.require(context, call.name, binding.resource)
            if (
                not self.agent.tools[call.name].enabled
                or self.agent.tools[call.name] != binding
                or binding.tool.definition != definition
            ):
                raise ContractError(ErrorCode.PERMISSION_DENIED, "Tool was disabled.")
            try:
                raw = await binding.tool.execute(call, context)
                return bounded_result(raw, self.agent.limits, binding.kind)
            except ContractError as error:
                delay = retry_delay(
                    error,
                    attempt,
                    self.agent.limits.retries,
                    safe=session_granted and binding.tool.definition.read_only,
                )
                if delay is None:
                    raise
                await asyncio.sleep(delay)
        raise AssertionError("Retry loop exhausted without an outcome")

    @staticmethod
    def _string(call: ToolCall, name: str, default: str | None = None) -> str:
        """Require a textual tool argument or use its supplied default.

        Parameters
        ----------
        call : ToolCall
            Tool invocation with its identifier, name, and arguments.
        name : str
            Field, tool, file, or fixture name.
        default : str | None
            Value to use when the argument is absent.

        Returns
        -------
        str
            Text produced by the operation.
        """
        value = call.arguments.get(name, default)
        if not isinstance(value, str):
            raise ContractError(ErrorCode.INVALID_INPUT, f"{name} must be text.")
        return value
