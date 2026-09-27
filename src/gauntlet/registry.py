"""Content-hash registry: the shared approve/verify primitive.

A registry maps a key to a human-approved content hash. Approval is a deliberate
human action; verification is a gate. Three consumers share this primitive:

    Phase 3  protected config files  key = repo-relative path
    Phase 4  Gherkin specs           key = feature file path
    Phase 5  equivalent mutants      key = hash of the mutation diff

Two rules every consumer inherits. A registry file must itself be a protected
path, or an agent approves its own changes. And MODIFIED must stay distinct from
UNAPPROVED: conflating them is how approval degrades into a rubber stamp.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from gauntlet.gates.base import write_text_atomic

SCHEMA_VERSION = 2
# The one version `gauntlet mutant migrate` can still read: version 1 keyed a
# literal mutant by its step line alone, so two literals on one line shared a key.
MIGRATABLE_VERSIONS = (1, SCHEMA_VERSION)
DIGEST_PREFIX = "sha256:"

NAMESPACE_SEPARATOR = ":"


def namespaced(namespace: str, key: str) -> str:
    """`config` + `gauntlet.toml` -> `config:gauntlet.toml`.

    One ledger holds every kind of human approval — configuration today, specs
    and equivalent mutants next — so keys carry the kind they belong to. One
    file to protect, one diff to review, one thing for a future dashboard to
    render as the approval state of the project.
    """
    return f"{namespace}{NAMESPACE_SEPARATOR}{key}"


def bare(key: str) -> str:
    """The key without its namespace, for human-facing messages."""
    _, _, rest = key.partition(NAMESPACE_SEPARATOR)
    return rest or key


def in_namespace(registry: Registry, namespace: str) -> Registry:
    prefix = namespace + NAMESPACE_SEPARATOR
    return Registry(entries={k: v for k, v in registry.entries.items() if k.startswith(prefix)})


def without_namespace(registry: Registry, namespace: str) -> Registry:
    prefix = namespace + NAMESPACE_SEPARATOR
    return Registry(entries={k: v for k, v in registry.entries.items() if not k.startswith(prefix)})


def verify_namespace(
    registry: Registry, namespace: str, subjects: Mapping[str, bytes | None]
) -> list[Finding]:
    """Verify one namespace only, so config checks never report specs as missing."""
    keyed = {namespaced(namespace, key): value for key, value in subjects.items()}
    return verify_all(in_namespace(registry, namespace), keyed)


class RegistryError(Exception):
    """The registry file is malformed. Maps to exit code 1, never 2."""


class Status(Enum):
    """Outcome of verifying one subject against its approved hash."""

    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    UNAPPROVED = "unapproved"
    MISSING = "missing"
    ABSENT = "absent"  # does not exist and never approved


@dataclass(frozen=True)
class Entry:
    key: str
    digest: str
    approved_at: str
    reason: str = ""
    reviewer: str = ""


@dataclass(frozen=True)
class Finding:
    key: str
    status: Status
    expected: str | None = None
    actual: str | None = None


@dataclass(frozen=True)
class Registry:
    entries: dict[str, Entry] = field(default_factory=dict)


def digest(content: bytes) -> str:
    """SHA-256 of the content, with CRLF normalized to LF.

    Normalizing keeps an approval valid across platforms and git autocrlf
    settings: a line-ending flip is not a change a human approved.
    """
    return DIGEST_PREFIX + hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_entry(key: str, value: Any, path: Path) -> Entry:
    if not isinstance(value, dict) or "digest" not in value:
        raise RegistryError(f"{path} entry {key!r} is malformed")
    return Entry(
        key=key,
        digest=str(value["digest"]),
        approved_at=str(value.get("approved_at", "")),
        reason=str(value.get("reason", "")),
        reviewer=str(value.get("reviewer", "")),
    )


def _version_of(raw: Any, path: Path) -> Any:
    if not isinstance(raw, dict):
        raise RegistryError(f"{path} is not a JSON object")
    return raw.get("version")


def _wrong_version(path: Path, version: Any) -> RegistryError:
    return RegistryError(f"{path} has schema version {version!r}, expected {SCHEMA_VERSION}")


def _parse_entries(raw: dict[str, Any], path: Path) -> dict[str, Entry]:
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        raise RegistryError(f"{path} has a malformed entries table")
    return {key: _parse_entry(key, value, path) for key, value in entries.items()}


def _parse(raw: Any, path: Path) -> dict[str, Entry]:
    version = _version_of(raw, path)
    if version == 1:
        raise RegistryError(
            f"{path} has schema version 1, expected {SCHEMA_VERSION}: "
            f"a human runs `gauntlet mutant migrate`"
        )
    if version != SCHEMA_VERSION:
        raise _wrong_version(path, version)
    return _parse_entries(raw, path)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"{path} is unreadable: {exc}") from exc


def load(path: Path) -> Registry:
    """Read a registry file. A missing file is an empty registry, not an error.

    The only loader any command other than `gauntlet mutant migrate` may call:
    a file at an older schema version is refused here with the remedy, never
    read as if its keys were current.
    """
    if not path.exists():
        return Registry()
    return Registry(entries=_parse(_read(path), path))


@dataclass(frozen=True)
class Loaded:
    """What `load_for_migration` read: the entries and the schema version they were keyed under."""

    version: int
    registry: Registry


def load_for_migration(path: Path) -> Loaded:
    """Read a registry file at any version `migrate` can rewrite, and say which it was.

    For `gauntlet mutant migrate` only; every other reader goes through `load`.
    The file must exist: the command says there is nothing to migrate before
    it asks.
    """
    raw = _read(path)
    version = _version_of(raw, path)
    if version not in MIGRATABLE_VERSIONS:
        raise _wrong_version(path, version)
    return Loaded(version=version, registry=Registry(entries=_parse_entries(raw, path)))


def approve(
    registry: Registry,
    key: str,
    content: bytes,
    when: str | None = None,
    reason: str = "",
    reviewer: str = "",
) -> Registry:
    """A new registry with `key` approved at its current content."""
    entry = Entry(
        key=key,
        digest=digest(content),
        approved_at=when or _now(),
        reason=reason,
        reviewer=reviewer,
    )
    return Registry(entries={**registry.entries, key: entry})


def _entry_payload(entry: Entry) -> dict[str, str]:
    payload = {"digest": entry.digest, "approved_at": entry.approved_at}
    if entry.reason:
        payload["reason"] = entry.reason
    if entry.reviewer:
        payload["reviewer"] = entry.reviewer
    return payload


def save(registry: Registry, path: Path) -> None:
    """Write deterministically: sorted keys, stable indent, trailing newline.

    This file is meant to be read in a diff, so its ordering must not churn.
    Temp file then replace: an interrupted save leaves the previous ledger intact.
    """
    payload = {
        "version": SCHEMA_VERSION,
        "entries": {key: _entry_payload(entry) for key, entry in sorted(registry.entries.items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def revoke(registry: Registry, key: str) -> Registry:
    """A new registry with `key` removed."""
    return Registry(entries={k: v for k, v in registry.entries.items() if k != key})


def verify(registry: Registry, key: str, content: bytes | None) -> Finding:
    """Compare one subject against its approved hash. `content` is None if it is gone.

    Four failing outcomes are kept distinct on purpose. MODIFIED means an approved
    subject changed; MISSING means an approved subject was deleted; UNAPPROVED means
    something exists that no human has signed off on. ABSENT — neither present nor
    approved — is none of those, and must not fail a gate.
    """
    entry = registry.entries.get(key)
    actual = digest(content) if content is not None else None
    if entry is None:
        status = Status.ABSENT if actual is None else Status.UNAPPROVED
        return Finding(key=key, status=status, actual=actual)
    if actual is None:
        return Finding(key=key, status=Status.MISSING, expected=entry.digest)
    status = Status.UNCHANGED if actual == entry.digest else Status.MODIFIED
    return Finding(key=key, status=status, expected=entry.digest, actual=actual)


def verify_all(registry: Registry, subjects: Mapping[str, bytes | None]) -> list[Finding]:
    """Verify every subject, plus every approved key the subjects omit (deleted)."""
    keys = sorted(set(subjects) | set(registry.entries))
    return [verify(registry, key, subjects.get(key)) for key in keys]


def describe(finding: Finding, noun: str = "file", command: str = "gauntlet lock") -> str:
    """Prescriptive message for a failing finding. Never called for UNCHANGED.
    `command` approves the caller's artifact: the protect gate's `gauntlet lock` by default."""
    if finding.status is Status.MODIFIED:
        return (
            f"{bare(finding.key)} changed since it was approved. This {noun} is the human's "
            f"artifact, not yours: revert the change, or explain why it should change "
            f"and let the human re-approve it with `{command}`."
        )
    if finding.status is Status.MISSING:
        return (
            f"{bare(finding.key)} was approved but no longer exists. Restore it, or ask the "
            f"human to remove its approval."
        )
    return (
        f"{bare(finding.key)} is not approved. A human must review it and run `{command}` "
        f"before it can be relied on."
    )
