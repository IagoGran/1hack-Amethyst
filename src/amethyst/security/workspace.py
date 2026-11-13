"""Scoped file reads and reviewed, descriptor-relative atomic file replacement."""

import difflib
import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from amethyst.domain.contracts import (
    ContractError,
    ErrorCode,
    FileChange,
    OperationContext,
    ProposedAction,
)
from amethyst.security.permissions import ApprovalEngine, PermissionService, fingerprint


@dataclass(frozen=True, slots=True)
class WorkspaceEdit:
    action: ProposedAction
    path: str
    content: str | None


class Workspace:
    """Linux/WSL descriptor-relative access; symlinks and special files are denied.

    Existing parent directories are required. A hostile host process with the same
    user's authority is outside the sandbox boundary; see B's threat model.
    """

    def __init__(
        self,
        root: Path,
        permissions: PermissionService,
        approvals: ApprovalEngine,
        max_bytes: int = 1_048_576,
    ) -> None:
        self.root = root.resolve(strict=True)
        self.permissions = permissions
        self.approvals = approvals
        self.max_bytes = max_bytes
        info = self.root.stat()
        self._identity = (info.st_dev, info.st_ino)

    def resource(self, path: str) -> str:
        return str(self.root.joinpath(*self._parts(path)))

    def _parts(self, path: str) -> tuple[str, ...]:
        value = PurePosixPath(path)
        parts = value.parts
        if (
            not parts
            or value.is_absolute()
            or ".." in parts
            or "\\" in path
            or "\x00" in path
            or ".git" in parts
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Path is outside the permitted workspace."
            )
        return parts

    @contextmanager
    def _parent(self, path: str) -> Iterator[tuple[int, str]]:
        parts = self._parts(path)
        descriptors: list[int] = []
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(fd)
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self._identity:
                raise ContractError(ErrorCode.CONFLICT, "Workspace location changed.")
            for part in parts[:-1]:
                fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                descriptors.append(fd)
            yield fd, parts[-1]
        except OSError:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED, "Workspace path is unavailable or unsafe."
            ) from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _read(self, parent: int, name: str) -> tuple[bytes | None, int]:
        try:
            fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
        except FileNotFoundError:
            return None, 0o600
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED,
                    "Only regular, unlinked workspace files are supported.",
                )
            data = handle.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise ContractError(
                    ErrorCode.INVALID_INPUT, "File exceeds the inspection limit."
                )
            return data, stat.S_IMODE(info.st_mode) & 0o777

    def read(self, path: str, context: OperationContext) -> str:
        self.permissions.require(context, "workspace.read", self.resource(path))
        with self._parent(path) as (parent, name):
            data, _ = self._read(parent, name)
        if data is None:
            raise ContractError(ErrorCode.NOT_FOUND, "Workspace file does not exist.")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Only UTF-8 text files are supported."
            ) from None

    def propose(
        self, path: str, content: str | None, context: OperationContext
    ) -> WorkspaceEdit:
        self.permissions.require(context, "workspace.read", self.resource(path))
        with self._parent(path) as (parent, name):
            original, mode = self._read(parent, name)
        try:
            before = original.decode("utf-8") if original is not None else ""
        except UnicodeDecodeError:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Only UTF-8 text files are supported."
            ) from None
        if content is not None and len(content.encode()) > self.max_bytes:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Proposed content exceeds the file limit."
            )
        if (original is None and content is None) or (
            original is not None and content == before
        ):
            raise ContractError(
                ErrorCode.CONFLICT, "The proposed change is already applied."
            )
        # Keep line endings visible, including a missing final newline.
        before_lines = before.splitlines(keepends=True)
        after_lines = (content or "").splitlines(keepends=True)
        diff = "".join(
            line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
            for line in difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{path}" if original is not None else "/dev/null",
                tofile=f"b/{path}" if content is not None else "/dev/null",
            )
        )
        # Empty file creation/deletion also needs a meaningful preview.
        if not diff:
            diff = (
                f"{'Create' if content is not None else 'Delete'} empty file: {path}\n"
            )
        change = FileChange(
            path,
            diff,
            hashlib.sha256(original).hexdigest() if original is not None else None,
        )
        scope = (str(self.root), self.resource(path))
        digest = fingerprint(
            {
                "root": str(self.root),
                "change": asdict(change),
                "content": content,
                "scope": scope,
                "mode": mode,
            }
        )
        action = ProposedAction(
            uuid4().hex,
            "workspace.edit",
            f"{'Delete' if content is None else 'Edit'} {path}",
            scope,
            digest,
            (change,),
            high_impact=content is None,
        )
        return WorkspaceEdit(action, path, content)

    async def apply(
        self, edit: WorkspaceEdit, approval_id: str, context: OperationContext
    ) -> None:
        # Rebuild against the current file; also recheck revoked read scope.
        current = self.propose(edit.path, edit.content, context)
        reviewed = await self.approvals.inspect(approval_id)
        if (
            replace(current.action, id=edit.action.id) != edit.action
            or edit.action not in reviewed.request.actions
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                "File or proposed diff changed; review again.",
            )
        with self._parent(edit.path) as (parent, name):
            original, mode = self._read(parent, name)
            actual_hash = (
                hashlib.sha256(original).hexdigest() if original is not None else None
            )
            if actual_hash != current.action.changes[0].base_sha256:
                raise ContractError(
                    ErrorCode.PERMISSION_DENIED, "File changed; review again."
                )
            await self.approvals.consume(
                approval_id,
                edit.action.id,
                current.action.fingerprint,
                context,
            )
            # No await after consumption: cancellation cannot abandon a partial write.
            if edit.content is None:
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
                return
            temporary = f".amethyst-{uuid4().hex}"
            try:
                fd = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    mode,
                    dir_fd=parent,
                )
                with os.fdopen(fd, "wb") as handle:
                    handle.write(edit.content.encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                # New files must still be absent; link is atomic and refuses overwrite.
                if original is None:
                    os.link(
                        temporary,
                        name,
                        src_dir_fd=parent,
                        dst_dir_fd=parent,
                        follow_symlinks=False,
                    )
                else:
                    os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                os.fsync(parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
