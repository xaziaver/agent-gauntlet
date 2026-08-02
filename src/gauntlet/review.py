"""Guided approval review.

The status inbox says what is waiting; this walks it. One item at a time, with
the actual change on screen, because approving something you have not looked at
is the rubber stamp the whole ledger exists to prevent.

Pure decision logic — no prompting, no printing. The CLI supplies answers and
renders; this decides what to show and what to record.
"""

from __future__ import annotations

import difflib
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from gauntlet import locking, registry, specs
from gauntlet.status import Pending

CONTEXT_LINES = 3
MAX_DIFF_LINES = 40


class Answer(Enum):
    APPROVE = "approve"
    SKIP = "skip"
    QUIT = "quit"


@dataclass(frozen=True)
class Item:
    """One pending decision, with the context needed to make it."""

    pending: Pending
    body: str
    needs_reason: bool

    @property
    def title(self) -> str:
        return f"[{self.pending.namespace}] {self.pending.subject} — {self.pending.status}"


def _git_show(root: Path, path: str) -> str | None:
    """The committed version of a file, if this is a git repo and it is tracked."""
    proc = subprocess.run(
        ["git", "show", f"HEAD:{path}"], cwd=root, capture_output=True, text=True, check=False
    )
    return proc.stdout if proc.returncode == 0 else None


def _render_diff(previous: str, current: str, path: str) -> str:
    lines = list(
        difflib.unified_diff(
            previous.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"approved/{path}",
            tofile=f"current/{path}",
            n=CONTEXT_LINES,
        )
    )
    if not lines:
        return "(content differs from the approved hash, but matches the last commit)"
    body = "".join(lines[:MAX_DIFF_LINES])
    extra = len(lines) - MAX_DIFF_LINES
    return body + (f"\n... {extra} more diff lines\n" if extra > 0 else "")


def diff_against_head(root: Path, path: str) -> str:
    """What changed, as a unified diff against the last commit.

    The ledger stores hashes, not content, so a diff needs another source for the
    previous version. Git is the pragmatic one; without it, say so plainly rather
    than implying the change is unknowable.
    """
    current_file = root / path
    if not current_file.is_file():
        return "(file no longer exists)"
    previous = _git_show(root, path)
    if previous is None:
        return "(no committed version to compare against — inspect the file directly)"
    return _render_diff(previous, current_file.read_text(encoding="utf-8"), path)


def _preview(root: Path, path: str) -> str:
    current_file = root / path
    if not current_file.is_file():
        return "(file no longer exists)"
    lines = current_file.read_text(encoding="utf-8").splitlines()
    shown = "\n".join(lines[:MAX_DIFF_LINES])
    return shown + (
        f"\n... {len(lines) - MAX_DIFF_LINES} more lines" if len(lines) > MAX_DIFF_LINES else ""
    )


def build_item(root: Path, item: Pending) -> Item:
    """Attach the context a human needs to judge one pending approval."""
    if item.status == registry.Status.MODIFIED.value:
        return Item(pending=item, body=diff_against_head(root, item.subject), needs_reason=True)
    if item.status == registry.Status.MISSING.value:
        body = (
            f"{item.subject} was approved but no longer exists. Approving here removes "
            f"the stale approval."
        )
        return Item(pending=item, body=body, needs_reason=False)
    return Item(pending=item, body=_preview(root, item.subject), needs_reason=False)


def apply(root: Path, item: Item, reason: str, reviewer: str) -> registry.Registry:
    """Record the decision. Returns the updated registry; the caller saves it."""
    if item.pending.namespace == specs.SPEC_NAMESPACE:
        return specs.approve(root, [root / item.pending.subject], reason, reviewer)
    return locking.approve_paths(root, [item.pending.subject], reason, reviewer)
