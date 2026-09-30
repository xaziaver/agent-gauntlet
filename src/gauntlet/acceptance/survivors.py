"""The survivor record: every mutant the last mutation stage saw survive.

The gate's diagnostic is capped, so the complete list a human is asked to judge
lives here, beside `acceptance-scope.json`. It is written unclassified — whether
a survivor is reviewed depends on the ledger at the moment it is read, not the
moment it was measured — and keyed by feature with the digest of the spec's
bytes, so a reader can tell a record that still describes the spec from one
that does not.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import registry
from gauntlet.acceptance.mutation import Mutant
from gauntlet.gates import base

RECORD = Path(".gauntlet") / "acceptance-survivors.json"


@dataclass(frozen=True)
class Measured:
    """One feature's survivors, and the spec they were measured against."""

    spec: str  # registry.digest of the spec's bytes, as its `spec:` approval holds it
    survivors: list[Mutant]


def measured(path: Path, survivors: list[Mutant]) -> Measured:
    return Measured(spec=registry.digest(path.read_bytes()), survivors=survivors)


def write(root: Path, features: dict[str, Measured]) -> None:
    """Replace the record whole, atomically: a reader never sees half of one."""
    record = {
        key: {"spec": m.spec, "survivors": [dataclasses.asdict(s) for s in m.survivors]}
        for key, m in features.items()
    }
    destination = root / RECORD
    destination.parent.mkdir(parents=True, exist_ok=True)
    base.write_text_atomic(destination, json.dumps(record, indent=2, sort_keys=True) + "\n")


def read(root: Path) -> dict[str, Any] | None:
    """The record as last written, or None: a record the tool cannot parse is no record."""
    try:
        loaded = json.loads((root / RECORD).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _describes_the_spec(root: Path, key: str, entry: dict[str, Any]) -> bool:
    """The record was measured against the spec as it is now on disk."""
    path = root / key
    return path.is_file() and registry.digest(path.read_bytes()) == entry["spec"]


def current(root: Path) -> dict[str, list[Mutant]]:
    """Each feature's recorded survivors, where the record still describes its spec.

    A feature whose spec moved yields nothing: its `spec` item is pending, and is
    the reason. A record that does not rebuild is no record, as one that does not parse.
    """
    record = read(root) or {}
    try:
        return {
            key: [Mutant(**item) for item in entry["survivors"]]
            for key, entry in record.items()
            if _describes_the_spec(root, key, entry)
        }
    except (TypeError, KeyError):
        return {}
