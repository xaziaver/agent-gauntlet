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
