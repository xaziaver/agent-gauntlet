"""The language seam. Everything above this line is language-independent."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunResult:
    passed: bool
    output: str
