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

ATTEMPTS_FILE = Path(".gauntlet") / "stop-attempts.json"
DEFAULT_MAX_ATTEMPTS = 3
UNKNOWN_SESSION = "unknown"


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
