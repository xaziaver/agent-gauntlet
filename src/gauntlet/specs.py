"""Spec approval: the human's artifact, in the shared ledger under `spec:`.

Specs are hash-locked rather than write-blocked. The agent drafts them — that is
its job — but an agent quietly editing an approved spec so its code passes is
the failure this exists to catch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gauntlet import locking, registry
from gauntlet import mutants as mutants_mod

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


class SpecError(Exception):
    """A spec command refused; the message is a whole sentence and nothing was written."""


@dataclass(frozen=True)
class Unapproved:
    """One withdrawn spec approval, and the mutant approvals that named it."""

    key: str
    exists: bool
    mutants: int  # kept while the spec exists, removed with it when it does not


@dataclass(frozen=True)
class Renamed:
    """Approvals carried from one path to another."""

    old: str
    new: str
    mutants: int
    differs: bool  # the content at `new` is not what was approved at `old`


def mutant_keys(approved: registry.Registry, key: str) -> list[str]:
    """Every `mutant:` key in the spec `key`, anchored on the subject separator so
    `x.feature` never claims `x.feature.bak`'s mutants."""
    prefix = f"{key}{mutants_mod.SUBJECT_SEPARATOR}"
    scoped = registry.in_namespace(approved, mutants_mod.MUTANT_NAMESPACE)
    return sorted(k for k in scoped.entries if registry.bare(k).startswith(prefix))


def unapprove(root: Path, paths: list[Path]) -> tuple[registry.Registry, list[Unapproved]]:
    """Withdraw each spec's approval; a spec that no longer exists takes its mutant
    approvals with it, because no command can reach them once it is gone. One
    refusal writes nothing for any path."""
    current = registry.load(locking.lock_path(root))
    done: list[Unapproved] = []
    for key, path in {key_for(root, p): p for p in paths}.items():
        current, withdrawn = _withdraw(current, key, path.is_file())
        done.append(withdrawn)
    return current, done


def _withdraw(
    approved: registry.Registry, key: str, exists: bool
) -> tuple[registry.Registry, Unapproved]:
    spec_key = registry.namespaced(SPEC_NAMESPACE, key)
    if spec_key not in approved.entries:
        raise SpecError(f"{key} is not approved; nothing written")
    dependents = mutant_keys(approved, key)
    gone = {spec_key} if exists else {spec_key, *dependents}
    kept = {k: v for k, v in approved.entries.items() if k not in gone}
    return registry.Registry(entries=kept), Unapproved(key, exists, len(dependents))


def _has_approvals(approved: registry.Registry, key: str) -> bool:
    return registry.namespaced(SPEC_NAMESPACE, key) in approved.entries or bool(
        mutant_keys(approved, key)
    )


def _refuse_rename(
    approved: registry.Registry, old: Path, new: Path, old_key: str, new_key: str
) -> None:
    if not new.is_file():
        raise SpecError(f"no such spec: {new_key}")
    if old.is_file():
        raise SpecError(
            f"{old_key} still exists; a rename moves approvals after a file that has moved. "
            f"To approve a copy, run `gauntlet spec approve {new_key}`"
        )
    if not _has_approvals(approved, old_key):
        raise SpecError(f"no approval names {old_key}; nothing written")
    if _has_approvals(approved, new_key):
        raise SpecError(f"{new_key} already has approvals; nothing written")


def rename(root: Path, old: Path, new: Path) -> tuple[registry.Registry, Renamed]:
    """Carry the spec approval and every mutant approval after a file that has moved,
    payloads untouched. The content is not checked: approved content, moved, then
    edited, reads MODIFIED at `new`, which is the truer state."""
    current = registry.load(locking.lock_path(root))
    old_key, new_key = key_for(root, old), key_for(root, new)
    _refuse_rename(current, old, new, old_key, new_key)
    entries = dict(current.entries)
    spec = entries.pop(registry.namespaced(SPEC_NAMESPACE, old_key), None)
    differs = spec is not None and spec.digest != registry.digest(new.read_bytes())
    if spec is not None:
        entries[registry.namespaced(SPEC_NAMESPACE, new_key)] = spec
    moved = mutant_keys(current, old_key)
    for key in moved:
        locator = registry.bare(key)[len(old_key) :]
        entries[registry.namespaced(mutants_mod.MUTANT_NAMESPACE, new_key + locator)] = entries.pop(
            key
        )
    renamed = Renamed(old=old_key, new=new_key, mutants=len(moved), differs=differs)
    return registry.Registry(entries=entries), renamed
