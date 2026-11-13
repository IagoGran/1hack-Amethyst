"""Background repository and fake-task operations for A3."""

import asyncio
from uuid import uuid4

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from amethyst.domain.contracts import (
    ContractError,
    Conversation,
    Message,
    StartTask,
    TaskFailure,
    TaskStateChanged,
    TextDelta,
)
from amethyst.domain.tasks import TaskStatus
from amethyst.ports.application import ApplicationService
from amethyst.ports.persistence import ConversationRepository


class ConversationWorker(QThread):
    """Run conversation repository operations away from Qt's event thread."""

    conversations_loaded = Signal(object)
    conversation_loaded = Signal(object)
    conversation_ready = Signal(str)
    message_delta = Signal(str)
    task_finished = Signal(bool)
    deleted = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        repository: ConversationRepository,
        service: ApplicationService,
        action: str,
        parent: QWidget,
        *,
        conversation_id: str | None = None,
        prompt: str | None = None,
    ) -> None:
        """Store one list, open, delete, or send operation for the worker."""
        super().__init__(parent)
        self._repository = repository
        self._service = service
        self._action = action
        self._conversation_id = conversation_id
        self._prompt = prompt

    def run(self) -> None:
        """Run one async operation in a worker-local event loop."""
        try:
            asyncio.run(self._execute())
        except ContractError as exc:
            self.failed.emit(str(exc))
            self._finish_failed_send()
        except Exception:
            self.failed.emit("The conversation preview operation failed.")
            self._finish_failed_send()

    async def _execute(self) -> None:
        """Dispatch the selected repository or chat operation."""
        if self._action == "list":
            await self._emit_list()
        elif self._action == "open":
            await self._open_conversation()
        elif self._action == "delete":
            await self._delete_conversation()
        elif self._action == "send":
            await self._send_message()

    async def _emit_list(self) -> None:
        """Read all saved conversations and forward them to the history view."""
        self.conversations_loaded.emit(await self._repository.list())

    async def _open_conversation(self) -> None:
        """Load a saved conversation snapshot for viewing and resumption."""
        if self._conversation_id:
            value = await self._repository.load(self._conversation_id)
            self.conversation_loaded.emit(value)

    async def _delete_conversation(self) -> None:
        """Delete one saved conversation, then refresh the visible list."""
        if self._conversation_id:
            await self._repository.delete(self._conversation_id)
            await self._emit_list()
            self.deleted.emit(self._conversation_id)

    async def _send_message(self) -> None:
        """Save a user turn, stream a fake reply, and persist the conversation."""
        if not self._prompt:
            return
        conversation = await self._load_or_create_conversation()
        user_message = Message("user", self._prompt)
        title = conversation.title
        if not conversation.messages:
            title = self._conversation_title(self._prompt)
        conversation = Conversation(
            conversation.id, title, (*conversation.messages, user_message)
        )
        await self._repository.save(conversation)
        self.conversation_ready.emit(conversation.id)
        await self._stream_reply(conversation)

    async def _load_or_create_conversation(self) -> Conversation:
        """Load the selected conversation or assign an ID to a new one."""
        if self._conversation_id:
            return await self._repository.load(self._conversation_id)
        return Conversation(str(uuid4()), "New conversation")

    async def _stream_reply(self, conversation: Conversation) -> None:
        """Stream fake output and save it after successful task completion."""
        prompt = self._prompt or ""
        task = await self._service.start_task(
            StartTask(conversation.id, prompt, "a3-preview")
        )
        response = ""
        completed = False
        failed = False
        async for event in self._service.events(task.id):
            payload = event.payload
            if isinstance(payload, TextDelta):
                response += payload.text
                self.message_delta.emit(payload.text)
            elif isinstance(payload, TaskFailure):
                failed = True
                self.failed.emit(payload.message)
            elif isinstance(payload, TaskStateChanged):
                completed = payload.status == TaskStatus.COMPLETED
        if completed and response:
            saved = Conversation(
                conversation.id,
                conversation.title,
                (*conversation.messages, Message("assistant", response)),
            )
            await self._repository.save(saved)
        self.task_finished.emit(completed and not failed)
        await self._emit_list()

    def _finish_failed_send(self) -> None:
        """Release the chat composer when a send operation raises early."""
        if self._action == "send":
            self.task_finished.emit(False)

    @staticmethod
    def _conversation_title(prompt: str) -> str:
        """Create a compact list title from the first user request."""
        single_line = " ".join(prompt.split())
        return single_line[:60] + ("…" if len(single_line) > 60 else "")
