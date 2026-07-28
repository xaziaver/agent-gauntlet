"""Applies the content registry to protected files on disk."""

from __future__ import annotations

from pathlib import Path

from gauntlet import registry
from gauntlet.config import LOCK_FILENAME

FAILING = frozenset({registry.Status.MODIFIED, registry.Status.MISSING, registry.Status.UNAPPROVED})


def lock_path(root: Path) -> Path:
    return root / LOCK_FILENAME


def read_subjects(root: Path, patterns: list[str]) -> dict[str, bytes | None]:
    """Current content of each verified path, or None where it does not exist."""
    subjects: dict[str, bytes | None] = {}
    for pattern in patterns:
        path = root / pattern
        subjects[pattern] = path.read_bytes() if path.is_file() else None
    return subjects


def approve_all(root: Path, patterns: list[str]) -> tuple[registry.Registry, list[str]]:
    """Approve every verified path that exists. Returns the registry and skipped keys."""
    current = registry.load(lock_path(root))
    skipped: list[str] = []
    for key, content in read_subjects(root, patterns).items():
        if content is None:
            skipped.append(key)
            continue
        current = registry.approve(current, key, content)
    return current, skipped


def failures(findings: list[registry.Finding]) -> list[registry.Finding]:
    """Findings that should fail a gate. Subjects that never existed are not findings."""
    return [f for f in findings if f.status in FAILING]
