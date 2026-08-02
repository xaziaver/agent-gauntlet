"""Spec approval: the human's artifact, in the shared ledger under `spec:`.

Specs are hash-locked rather than write-blocked. The agent drafts them — that is
its job — but an agent quietly editing an approved spec so its code passes is
the failure this exists to catch.
"""

from __future__ import annotations

from pathlib import Path

from gauntlet import locking, registry

SPEC_NAMESPACE = "spec"
FEATURE_GLOB = "**/*.feature"


def discover(root: Path, features_dir: str) -> list[Path]:
    directory = root / features_dir
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob(FEATURE_GLOB) if p.is_file())


def key_for(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_subjects(root: Path, paths: list[Path]) -> dict[str, bytes | None]:
    return {key_for(root, p): (p.read_bytes() if p.is_file() else None) for p in paths}


def approve(
    root: Path, paths: list[Path], reason: str = "", reviewer: str = ""
) -> registry.Registry:
    """Approve specific specs, leaving other namespaces and other specs untouched."""
    current = registry.load(locking.lock_path(root))
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        current = registry.approve(
            current,
            registry.namespaced(SPEC_NAMESPACE, key_for(root, path)),
            path.read_bytes(),
            reason=reason,
            reviewer=reviewer,
        )
    return current


def verify(root: Path, paths: list[Path], approved: registry.Registry) -> list[registry.Finding]:
    subjects = read_subjects(root, paths)
    return locking.failures(registry.verify_namespace(approved, SPEC_NAMESPACE, subjects))


def approved_keys(approved: registry.Registry) -> list[str]:
    return sorted(registry.bare(k) for k in registry.in_namespace(approved, SPEC_NAMESPACE).entries)


def status_lines(root: Path, features_dir: str, approved: registry.Registry) -> list[str]:
    """One line per spec: its status and its path, discovered plus previously approved."""
    found = discover(root, features_dir)
    problems = {registry.bare(f.key): f.status.value for f in verify(root, found, approved)}
    keys = sorted(set(approved_keys(approved)) | {key_for(root, p) for p in found})
    return [f"{problems.get(key, 'approved'):<12} {key}" for key in keys]
