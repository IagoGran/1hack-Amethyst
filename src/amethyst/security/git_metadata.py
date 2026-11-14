"""Read a bounded local branch catalog without invoking Git commands."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GitBranch:
    """Safe branch display metadata from a local repository.

    Parameters
    ----------
    name : str
        Local branch name.
    commit : str
        Short branch tip identifier.
    current : bool
        Whether this branch is referenced by HEAD.
    """

    name: str
    commit: str
    current: bool


def list_branches(root: Path) -> tuple[GitBranch, ...]:
    """List branch names and tip IDs from repository metadata under ``root``.

    Parameters
    ----------
    root : Path
        Authorized workspace directory.

    Returns
    -------
    tuple of GitBranch
        Bounded branch metadata, without source or commit contents.
    """
    metadata = root / ".git"
    if metadata.is_symlink() or not metadata.exists():
        return ()
    if metadata.is_file():
        metadata = _worktree_git_dir(metadata, root)
        if metadata is None:
            return ()
    if not metadata.is_dir() or not metadata.resolve().is_relative_to(root.resolve()):
        return ()
    current_ref = _current_ref(metadata)
    refs = _loose_refs(metadata)
    refs.update(_packed_refs(metadata))
    branches = [
        GitBranch(name, commit[:7], name == current_ref)
        for name, commit in refs.items()
        if name.startswith("refs/heads/") and len(commit) == 40
    ]
    ordered = sorted(branches, key=lambda branch: (not branch.current, branch.name))
    return tuple(ordered[:200])


def _worktree_git_dir(pointer: Path, root: Path) -> Path | None:
    """Resolve an in-workspace ``.git`` pointer without following escapes.

    Parameters
    ----------
    pointer : Path
        Git pointer file located at the selected workspace root.
    root : Path
        Authorized workspace boundary.

    Returns
    -------
    Path or None
        In-bound Git metadata directory, or ``None`` when invalid.
    """
    try:
        content = pointer.read_text(encoding="utf-8", errors="strict").strip()
        if not content.startswith("gitdir:"):
            return None
        candidate = (root / content.partition(":")[2].strip()).resolve(strict=True)
        return candidate if candidate.is_relative_to(root.resolve()) else None
    except (OSError, UnicodeError, ValueError):
        return None


def _current_ref(metadata: Path) -> str | None:
    """Return the active symbolic branch name when HEAD names one.

    Parameters
    ----------
    metadata : Path
        In-bound Git metadata directory.

    Returns
    -------
    str or None
        Symbolic branch ref or ``None`` for detached/invalid HEAD.
    """
    head = metadata / "HEAD"
    if head.is_symlink():
        return None
    try:
        value = head.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    return value[5:] if value.startswith("ref: ") else None


def _loose_refs(metadata: Path) -> dict[str, str]:
    """Read bounded regular loose refs while rejecting symlink traversal.

    Parameters
    ----------
    metadata : Path
        In-bound Git metadata directory.

    Returns
    -------
    dict
        Bounded branch ref names mapped to commit IDs.
    """
    root = metadata / "refs" / "heads"
    if root.is_symlink() or not root.is_dir():
        return {}
    refs = {}
    scanned = 0
    for path in root.rglob("*"):
        scanned += 1
        if scanned > 1_000 or len(refs) >= 200:
            break
        if path.is_symlink() or not path.is_file():
            continue
        try:
            relative = path.relative_to(metadata).as_posix()
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(metadata.resolve()):
                continue
            commit = path.read_text(encoding="ascii").strip()
            if len(commit) == 40 and all(char in "0123456789abcdef" for char in commit):
                refs[relative] = commit
        except (OSError, UnicodeError, ValueError):
            continue
    return refs


def _packed_refs(metadata: Path) -> dict[str, str]:
    """Read branch tips from a bounded Git packed-refs metadata file.

    Parameters
    ----------
    metadata : Path
        In-bound Git metadata directory.

    Returns
    -------
    dict
        Parsed packed ref names mapped to commit IDs.
    """
    packed = metadata / "packed-refs"
    if packed.is_symlink():
        return {}
    try:
        with packed.open(encoding="ascii") as stream:
            content = stream.read(1_000_000)
    except (OSError, UnicodeError):
        return {}
    refs = {}
    for line in content.splitlines():
        pieces = line.split(" ", 1)
        if len(pieces) == 2 and len(pieces[0]) == 40:
            refs[pieces[1]] = pieces[0]
    return refs
