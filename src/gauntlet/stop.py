"""Attempt tracking for the Stop hook.

A Stop hook that exits 2 whenever the gates fail will loop forever if the agent
cannot satisfy them. Counting attempts per session lets the loop give up and ask
for a human, which is the right outcome for a genuinely wrong threshold or a
broken tool.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gauntlet.gates.base import GateResult

ATTEMPTS_FILE = Path(".gauntlet") / "stop-attempts.json"
DEFAULT_MAX_ATTEMPTS = 3
UNKNOWN_SESSION = "unknown"
APPROVAL_SYMBOLS = frozenset({"unapproved", "modified", "missing"})


def attempts_path(root: Path) -> Path:
    return root / ATTEMPTS_FILE


def session_id(payload: dict[str, Any]) -> str:
    """Sessions are counted separately; a missing id shares one bucket."""
    value = payload.get("session_id")
    return str(value) if value else UNKNOWN_SESSION


def load_attempts(path: Path) -> dict[str, int]:
    """Attempt counts by session. Unreadable state resets rather than crashing."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}


def save_attempts(state: dict[str, int], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_failure(state: dict[str, int], session: str) -> tuple[dict[str, int], int]:
    """A new state with this session incremented, and the new count."""
    count = state.get(session, 0) + 1
    return {**state, session: count}, count


def clear_session(state: dict[str, int], session: str) -> dict[str, int]:
    """A new state with this session forgotten, so the next failure starts over."""
    return {k: v for k, v in state.items() if k != session}


def should_escalate(count: int, max_attempts: int) -> bool:
    """True once the agent has been bounced max_attempts times without succeeding."""
    return count >= max_attempts


def escalation_message(count: int, lines: str) -> str:
    return (
        f"Gauntlet gates still failing after {count} attempts — stopping the retry loop "
        f"and handing this to you.\n{lines}"
    )


def _approval_only(result: GateResult) -> bool:
    """Every diagnostic of a failing gate is an approval finding, and there is at least one."""
    if result.error is not None or not result.diagnostics:
        return False
    return all(d.symbol in APPROVAL_SYMBOLS for d in result.diagnostics)


def human_blocked(results: list[GateResult]) -> bool:
    """True when every failure needs a human's approval and nothing needs the agent.

    A gate that crashed, failed with no diagnostics, or reported any other kind of
    finding is the agent's to act on, so the run is not blocked.
    """
    failed = [r for r in results if not r.passed]
    return bool(failed) and all(_approval_only(r) for r in failed)


def blocked_message(lines: str) -> str:
    """Names no command: each line of the report already carries the one for its cause."""
    return (
        "Gauntlet is blocked on a human: the failures below need a human's action — an "
        "approval or a ledger repair, named in each line — not code. Nothing here is for "
        "the agent.\n" + lines
    )
