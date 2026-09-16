"""Backups of specs under in-place mutation, and the strands a killed run leaves."""

from __future__ import annotations

from pathlib import Path

BACKUP_DIR = Path(".gauntlet") / "mutation-backup"


def backup(root: Path, path: Path, text: str) -> None:
    """Keep a copy on disk so a crash mid-mutation is recoverable by hand."""
    destination = root / BACKUP_DIR / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
