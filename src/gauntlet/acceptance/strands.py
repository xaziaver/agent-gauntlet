"""Backups of specs under in-place mutation, and the strands a killed run leaves.

A backup exists only between a spec's first mutant write and its restore. One on
disk at the start of a run therefore means a run died in that window — a strand —
and the spec is put back from it before anything else reads the spec.
"""

from __future__ import annotations

from pathlib import Path

from gauntlet.gates import base

BACKUP_DIR = Path(".gauntlet") / "mutation-backup"


def _mirror(root: Path, path: Path) -> Path:
    """The backup's location mirrors the spec's path, so two specs of one basename never share."""
    return root / BACKUP_DIR / path.resolve().relative_to(root.resolve())


def backup(root: Path, path: Path, text: str) -> None:
    """Keep a copy on disk so a killed run can be undone at the next start."""
    destination = _mirror(root, path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def discard(root: Path, path: Path) -> None:
    """Remove the spec's backup, if any: the restore is done, so its presence would lie."""
    _remove(root, _mirror(root, path))


def _remove(root: Path, copy: Path) -> None:
    """Unlink one backup and every directory that leaves empty, up to BACKUP_DIR itself."""
    copy.unlink(missing_ok=True)
    top = root / BACKUP_DIR
    parent = copy.parent
    while parent.is_relative_to(top) and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def _stranded(copy: Path, target: Path, features_dir: Path) -> bool:
    """A backup is a strand only when its spec exists under features/ and differs from it."""
    if not target.is_file() or not target.resolve().is_relative_to(features_dir.resolve()):
        return False
    return target.read_bytes() != copy.read_bytes()


def _backups(top: Path) -> list[Path]:
    return sorted(item for item in top.rglob("*") if item.is_file())


def restore_all(root: Path, features_dir: Path) -> int:
    """Put every stranded spec back from its backup and discard every backup.

    Counts the specs whose content differed. A backup whose target is gone, or lies
    outside the features directory, cannot be a strand and is only discarded.
    """
    top = root / BACKUP_DIR
    if not top.is_dir():
        return 0
    restored = 0
    for copy in _backups(top):
        target = root / copy.relative_to(top)
        if _stranded(copy, target, features_dir):
            base.write_text_atomic(target, copy.read_text(encoding="utf-8"))
            restored += 1
        _remove(root, copy)
    return restored
