"""The language seam. Everything above this line is language-independent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RunResult:
    passed: bool
    output: str


class AcceptanceAdapter(Protocol):
    def run_acceptance(self, root: Path, steps: Path, timeout: int) -> RunResult: ...
