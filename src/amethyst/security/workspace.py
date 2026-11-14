"""Scoped file reads and reviewed, descriptor-relative atomic file replacement."""

import difflib
import hashlib
import json
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
    directories: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceDirectory:
    action: ProposedAction
    directories: tuple[str, ...]


class Workspace:
    """Linux/WSL descriptor-relative access; symlinks and special files are denied.

    Missing parent directories can be created only as part of an approved edit.
    A hostile host process with the same user's authority is outside the sandbox
    boundary; see B's threat model.
    """

    def __init__(
        self,
        root: Path,
        permissions: PermissionService,
        approvals: ApprovalEngine,
        max_bytes: int = 1_048_576,
    ) -> None:
        """Bind scoped file access to the workspace identity and security session.

        Parameters
        ----------
        root : Path
            Application-owned data directory or approved workspace root.
        permissions : PermissionService
            Session-scoped read permission service.
        approvals : ApprovalEngine
            Session-scoped exact-action approval service.
        max_bytes : int
            Maximum workspace file size permitted for inspection or editing.

        Returns
        -------
        None
        """
        self.root = root.resolve(strict=True)
        self.permissions = permissions
        self.approvals = approvals
        self.max_bytes = max_bytes
        info = self.root.stat()
        self._identity = (info.st_dev, info.st_ino)

    def resource(self, path: str) -> str:
        """Resolve the permission resource for a validated relative file path.

        Parameters
        ----------
        path : str
            Scoped filesystem location used by the operation.

        Returns
        -------
        str
            Text produced by the operation.
        """
        return str(self.root.joinpath(*self._parts(path)))

    def _parts(self, path: str) -> tuple[str, ...]:
        """Validate a relative path without traversal or protected Git access.

        Parameters
        ----------
        path : str
            Scoped filesystem location used by the operation.

        Returns
        -------
        tuple[str, ...]
            Value produced by the operation.
        """
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
    def _parent(
        self,
        path: str,
        *,
        missing: list[str] | None = None,
        create: bool = False,
        created: list[str] | None = None,
    ) -> Iterator[tuple[int, str]]:
        """Open validated parent descriptors without following symbolic links.

        Parameters
        ----------
        path : str
            Scoped filesystem location used by the operation.

        Yields
        ------
        tuple[int, str]
            Ordered values produced by the operation.
        """
        parts = self._parts(path)
        descriptors: list[int] = []
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(fd)
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self._identity:
                raise ContractError(ErrorCode.CONFLICT, "Workspace location changed.")
            for index, part in enumerate(parts[:-1]):
                try:
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=fd,
                    )
                except FileNotFoundError:
                    if create:
                        try:
                            os.mkdir(part, 0o700, dir_fd=fd)
                            if created is not None:
                                created.append("/".join(parts[: index + 1]))
                        except FileExistsError:
                            pass
                        child = os.open(
                            part,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd,
                        )
                    elif missing is not None:
                        missing.extend(
                            "/".join(parts[: position + 1])
                            for position in range(index, len(parts) - 1)
                        )
                        yield -1, parts[-1]
                        return
                    else:
                        raise
                descriptors.append(child)
                fd = child
            yield fd, parts[-1]
        except OSError:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                f"Workspace path '{path}' is unavailable or unsafe. Check that "
                "its parent exists and that no path component is a symlink or "
                "non-directory.",
            ) from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _read(self, parent: int, name: str) -> tuple[bytes | None, int]:
        """Read a bounded regular file through its verified parent descriptor.

        Parameters
        ----------
        parent : int
            Owning widget, descriptor, or temporary-data directory.
        name : str
            Field, tool, file, or fixture name.

        Returns
        -------
        tuple[bytes | None, int]
            Value produced by the operation.
        """
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

    def _remove_empty_directories(self, paths: list[str]) -> None:
        """Best-effort cleanup of empty directories from a failed approved edit."""
        for path in reversed(paths):
            try:
                with self._parent(path) as (parent, name):
                    os.rmdir(name, dir_fd=parent)
                    os.fsync(parent)
            except (OSError, ContractError):
                pass

    def read(self, path: str, context: OperationContext) -> str:
        """Read a permitted workspace file as bounded UTF-8 text.

        Parameters
        ----------
        path : str
            Scoped filesystem location used by the operation.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        str
            Text produced by the operation.
        """
        self.permissions.require(context, "workspace.read", self.resource(path))
        with self._parent(path) as (parent, name):
            data, _ = self._read(parent, name)
        if data is None:
            raise ContractError(
                ErrorCode.NOT_FOUND,
                f"Workspace file '{path}' does not exist; list its parent folder "
                "or choose an existing file.",
            )
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise ContractError(
                ErrorCode.INVALID_INPUT, "Only UTF-8 text files are supported."
            ) from None

    def list(self, path: str, context: OperationContext) -> str:
        """List bounded workspace entries without following symbolic links."""
        relative = "." if path in ("", ".") else path
        parts = () if relative == "." else self._parts(relative)
        resource = str(self.root.joinpath(*parts))
        self.permissions.require(context, "workspace.read", resource)
        descriptors: list[int] = []
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(fd)
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != self._identity:
                raise ContractError(ErrorCode.CONFLICT, "Workspace location changed.")
            for part in parts:
                fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                descriptors.append(fd)
            names = sorted(name for name in os.listdir(fd) if name != ".git")
            entries = []
            for name in names[:200]:
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                kind = (
                    "directory"
                    if stat.S_ISDIR(info.st_mode)
                    else "file"
                    if stat.S_ISREG(info.st_mode)
                    else "symlink"
                    if stat.S_ISLNK(info.st_mode)
                    else "other"
                )
                entries.append({"name": name, "type": kind})
            return json.dumps(
                {
                    "workspace": str(self.root),
                    "path": relative,
                    "entries": entries,
                    "truncated": len(names) > len(entries),
                },
                ensure_ascii=False,
            )
        except OSError:
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                f"Workspace directory '{relative}' is unavailable or unsafe. "
                "Check that it exists and contains no symlink path components.",
            ) from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def propose_directory(
        self, path: str, context: OperationContext
    ) -> WorkspaceDirectory:
        """Prepare a reviewed proposal to create a workspace directory tree.

        Parameters
        ----------
        path : str
            Workspace-relative directory to create.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        WorkspaceDirectory
            Exact action and ordered directories covered by its approval.
        """
        self.permissions.require(context, "workspace.read", self.resource(path))
        missing: list[str] = []
        with self._parent(path, missing=missing) as (parent, name):
            if parent >= 0:
                try:
                    os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ContractError(
                        ErrorCode.CONFLICT,
                        f"Cannot create '{path}': a file or directory already "
                        "exists there.",
                    )
        directories = tuple((*missing, path))
        change = FileChange(
            path,
            "".join(f"Create directory: {directory}\n" for directory in directories),
            None,
        )
        scope = (str(self.root),) + tuple(
            self.resource(directory) for directory in directories
        )
        action = ProposedAction(
            uuid4().hex,
            "workspace.mkdir",
            f"Create directory tree: {', '.join(directories)}",
            scope,
            fingerprint({"root": str(self.root), "directories": directories}),
            (change,),
        )
        return WorkspaceDirectory(action, directories)

    async def create_directory(
        self,
        proposal: WorkspaceDirectory,
        approval_id: str,
        context: OperationContext,
    ) -> None:
        """Recheck and create the exact directory tree after approval.

        Parameters
        ----------
        proposal : WorkspaceDirectory
            Directory action bound to the user's reviewed proposal.
        approval_id : str
            Identifier of the reviewed approval record.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        None
        """
        current = self.propose_directory(proposal.directories[-1], context)
        reviewed = await self.approvals.inspect(approval_id)
        if (
            replace(current.action, id=proposal.action.id) != proposal.action
            or proposal.action not in reviewed.request.actions
        ):
            raise ContractError(
                ErrorCode.PERMISSION_DENIED,
                "Directory state changed; review the updated creation proposal.",
            )
        await self.approvals.consume(
            approval_id,
            proposal.action.id,
            current.action.fingerprint,
            context,
        )
        created: list[str] = []
        try:
            for directory in proposal.directories:
                with self._parent(directory, create=True, created=created) as (
                    parent,
                    name,
                ):
                    os.mkdir(name, 0o700, dir_fd=parent)
                    created.append(directory)
                    os.fsync(parent)
        except BaseException:
            self._remove_empty_directories(created)
            raise

    def propose(
        self, path: str, content: str | None, context: OperationContext
    ) -> WorkspaceEdit:
        """Bind a meaningful file diff and current file state to an exact action.

        Parameters
        ----------
        path : str
            Scoped filesystem location used by the operation.
        content : str | None
            Text content to display, persist, or return.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        WorkspaceEdit
            Exact reviewed file change and its bound action.
        """
        self.permissions.require(context, "workspace.read", self.resource(path))
        missing_directories: list[str] = []
        with self._parent(path, missing=missing_directories) as (parent, name):
            original, mode = (None, 0o600) if parent < 0 else self._read(parent, name)
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
            "".join(
                f"Create directory: {directory}\n" for directory in missing_directories
            )
            + diff,
            hashlib.sha256(original).hexdigest() if original is not None else None,
        )
        directories = tuple(missing_directories)
        scope = (str(self.root), self.resource(path)) + tuple(
            self.resource(directory) for directory in directories
        )
        digest = fingerprint(
            {
                "root": str(self.root),
                "change": asdict(change),
                "content": content,
                "scope": scope,
                "mode": mode,
                "directories": directories,
            }
        )
        action = ProposedAction(
            uuid4().hex,
            "workspace.edit",
            f"{'Delete' if content is None else 'Edit'} {path}"
            + (f"; create {', '.join(directories)}" if directories else ""),
            scope,
            digest,
            (change,),
            high_impact=content is None,
        )
        return WorkspaceEdit(action, path, content, directories)

    async def apply(
        self, edit: WorkspaceEdit, approval_id: str, context: OperationContext
    ) -> None:
        # Rebuild against the current file; also recheck revoked read scope.
        """Recheck the reviewed file state and consume approval before atomic mutation.

        Parameters
        ----------
        edit : WorkspaceEdit
            Proposed workspace change bound to its reviewed action.
        approval_id : str
            Identifier of the reviewed approval record.
        context : OperationContext
            Task/session scope, remaining timeout, and output limits.

        Returns
        -------
        None
        """
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
        missing_directories: list[str] = []
        with self._parent(edit.path, missing=missing_directories) as (parent, name):
            original, mode = (None, 0o600) if parent < 0 else self._read(parent, name)
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
            created: list[str] = []
            parent_context = None
            try:
                if edit.directories:
                    parent_context = self._parent(
                        edit.path, create=True, created=created
                    )
                    parent, name = parent_context.__enter__()
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
                    if original is None:
                        os.link(
                            temporary,
                            name,
                            src_dir_fd=parent,
                            dst_dir_fd=parent,
                            follow_symlinks=False,
                        )
                    else:
                        os.replace(
                            temporary, name, src_dir_fd=parent, dst_dir_fd=parent
                        )
                    os.fsync(parent)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
            except BaseException:
                self._remove_empty_directories(created)
                raise
            finally:
                if parent_context is not None:
                    parent_context.__exit__(None, None, None)
