"""Protected-path guard for agent hooks.

Reads a PreToolUse hook payload on stdin and blocks writes to the files that
define the gates themselves. A threshold an agent can edit is not a threshold.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

# Keys the file-editing tools use for their target path.
FILE_PATH_KEYS = ("file_path", "notebook_path", "path")


class PayloadError(Exception):
    """The hook payload could not be understood."""


def parse_payload(raw: str) -> dict[str, Any]:
    """The JSON object Claude Code sends on stdin."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PayloadError(f"hook payload is not valid JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise PayloadError("hook payload is not a JSON object")
    return payload


def target_path(payload: dict[str, Any]) -> str | None:
    """The file the tool is about to write, or None for tools that write no file."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in FILE_PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def relative_to_root(path_str: str, root: Path) -> str | None:
    """Root-relative POSIX path, or None when the target lies outside the project."""
    path = Path(path_str)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def matches(rel: str, pattern: str) -> bool:
    """True when a root-relative path is the protected path, lives under it, or globs to it."""
    cleaned = pattern.rstrip("/")
    return rel == cleaned or rel.startswith(f"{cleaned}/") or fnmatch(rel, pattern)


def blocked_by(rel: str, patterns: Sequence[str]) -> str | None:
    """The first pattern this path violates, or None."""
    return next((pattern for pattern in patterns if matches(rel, pattern)), None)


def refusal(rel: str, pattern: str) -> str:
    return (
        f"Blocked: {rel} is a protected Gauntlet file (matched `{pattern}`).\n"
        f"Quality thresholds, approved specs, and hook configuration are the human's "
        f"artifacts, not yours. Fix the code so the existing gates pass instead of "
        f"changing what the gates require.\n"
        f"If you believe a threshold is genuinely wrong, say so in your response and "
        f"let the human decide."
    )


def decide(payload: dict[str, Any], root: Path, patterns: Sequence[str]) -> str | None:
    """The refusal message to print on stderr, or None to allow the tool call."""
    raw_path = target_path(payload)
    if raw_path is None:
        return None
    rel = relative_to_root(raw_path, root)
    if rel is None:
        return None
    pattern = blocked_by(rel, patterns)
    if pattern is None:
        return None
    return refusal(rel, pattern)
