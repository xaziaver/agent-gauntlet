"""Applies the content registry to protected files on disk."""

from __future__ import annotations

from pathlib import Path

from gauntlet import config as config_mod
from gauntlet import registry

FAILING = frozenset({registry.Status.MODIFIED, registry.Status.MISSING, registry.Status.UNAPPROVED})

CONFIG_NAMESPACE = "config"


def lock_path(root: Path) -> Path:
    return root / config_mod.LOCK_FILENAME


def read_subjects(root: Path, patterns: list[str]) -> dict[str, bytes | None]:
    """Current content of each verified path, or None where it does not exist."""
    subjects: dict[str, bytes | None] = {}
    for pattern in patterns:
        path = root / pattern
        subjects[pattern] = path.read_bytes() if path.is_file() else None
    return subjects


def approve_all(root: Path, patterns: list[str]) -> tuple[registry.Registry, list[str]]:
    """Approve every verified path that exists, replacing the config namespace.

    Replacing rather than merging means dropping a path from verified_paths also
    drops its approval, instead of leaving a stale entry behind forever.
    """
    current = registry.without_namespace(registry.load(lock_path(root)), CONFIG_NAMESPACE)
    skipped: list[str] = []
    for key, content in read_subjects(root, patterns).items():
        if content is None:
            skipped.append(key)
            continue
        current = registry.approve(current, registry.namespaced(CONFIG_NAMESPACE, key), content)
    return current, skipped


def verify_config(
    root: Path, patterns: list[str], approved: registry.Registry
) -> list[registry.Finding]:
    subjects = read_subjects(root, patterns)
    return failures(registry.verify_namespace(approved, CONFIG_NAMESPACE, subjects))


def failures(findings: list[registry.Finding]) -> list[registry.Finding]:
    """Findings that should fail a gate. Subjects that never existed are not findings."""
    return [f for f in findings if f.status in FAILING]
