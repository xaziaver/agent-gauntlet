"""Append-only event log.

The gates already answer "what is the state now". A dashboard also needs "what
is happening" — so every command emits a line here, and any live view becomes a
tail-and-render rather than a special path into internals.

Two rules. Writing an event must never fail the caller: a broken log is a lost
line, not a broken gate. And the file is bounded, because an always-on agent
loop would otherwise grow it without limit.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVENTS_FILE = Path(".gauntlet") / "events.jsonl"
SCHEMA_VERSION = 1
MAX_BYTES = 5_000_000
ROTATED_SUFFIX = ".1"

RUN_STARTED = "run.started"
RUN_FINISHED = "run.finished"
GATE_FINISHED = "gate.finished"
APPROVAL_NEEDED = "approval.needed"
APPROVAL_GRANTED = "approval.granted"
AGENT_BLOCKED = "agent.blocked"
AGENT_ITERATION = "agent.iteration"
AGENT_ESCALATED = "agent.escalated"


@dataclass(frozen=True)
class Event:
    kind: str
    data: dict[str, Any]
    at: str
    run: str
    version: int = SCHEMA_VERSION

    def to_line(self) -> str:
        """Envelope fields last: a reader must always be able to trust them."""
        payload = {
            **self.data,
            "v": self.version,
            "at": self.at,
            "run": self.run,
            "kind": self.kind,
        }
        return json.dumps(payload, sort_keys=True, default=str) + "\n"


def events_path(root: Path) -> Path:
    return root / EVENTS_FILE


def new_run_id() -> str:
    """Correlates every event from one command invocation."""
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"


def build(event: str, run_id: str, data: dict[str, Any]) -> Event:
    return Event(
        kind=event, data=data, at=datetime.now(UTC).isoformat(timespec="seconds"), run=run_id
    )


def _rotate(path: Path, max_bytes: int) -> None:
    if path.exists() and path.stat().st_size >= max_bytes:
        path.replace(path.with_suffix(path.suffix + ROTATED_SUFFIX))


class Log:
    """A run's event sink. Disabled instances are silently inert."""

    def __init__(self, root: Path | None, run: str | None = None, enabled: bool = True) -> None:
        self.root = root
        self.run = run or new_run_id()
        self.enabled = enabled and root is not None

    def emit(self, event: str, **data: Any) -> None:
        """Write one event. Never raises: a lost line beats a broken gate."""
        if not self.enabled or self.root is None:
            return
        path = events_path(self.root)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate(path, MAX_BYTES)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(build(event, self.run, data).to_line())
        except OSError:
            return


def disabled() -> Log:
    return Log(root=None, enabled=False)


def read(path: Path, limit: int = 0) -> list[dict[str, Any]]:
    """Parse the log, skipping unreadable lines. Newest last; limit 0 means all."""
    if not path.is_file():
        return []
    parsed: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            parsed.append(item)
    return parsed[-limit:] if limit > 0 else parsed
