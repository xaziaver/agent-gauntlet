"""Environment checks: is every enabled gate actually able to run?

Hooks fail open by design — a broken Gauntlet exits 1, Claude Code shrugs, and
enforcement silently disappears while the session looks normal. This is the
command that makes that state visible.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass

CHECK_ORDER = ("git", "ruff", "mypy", "radon", "pytest", "pytest-cov", "pytest-bdd", "jscpd")

# Which gates need which tool. Gates absent here need only the standard library.
GATES_BY_TOOL = {
    "git": ("--changed",),
    "ruff": ("static",),
    "mypy": ("static",),
    "radon": ("complexity", "crap"),
    "pytest": ("tests",),
    "pytest-cov": ("coverage", "crap"),
    "pytest-bdd": ("acceptance",),
    "jscpd": ("duplication",),
}

MODULES = {
    "mypy": "mypy",
    "pytest": "pytest",
    "pytest-cov": "pytest_cov",
    "pytest-bdd": "pytest_bdd",
}


@dataclass(frozen=True)
class Check:
    tool: str
    ok: bool
    detail: str

    @property
    def gates(self) -> tuple[str, ...]:
        return GATES_BY_TOOL[self.tool]


def _on_path(executable: str) -> Check:
    found = shutil.which(executable)
    detail = found or "not on PATH — gates depending on it will error, not pass"
    return Check(tool=executable, ok=found is not None, detail=detail)


def _importable(tool: str) -> Check:
    """Tools invoked as `python -m` must be importable by THIS interpreter."""
    module = MODULES[tool]
    found = importlib.util.find_spec(module) is not None
    detail = (
        f"importable by {sys.executable}"
        if found
        else (f"module {module!r} not importable by {sys.executable}")
    )
    return Check(tool=tool, ok=found, detail=detail)


def run_checks(enabled_gates: list[str]) -> list[Check]:
    """One check per tool any enabled gate (or --changed) depends on."""
    relevant = set(enabled_gates) | {"--changed"}
    checks: list[Check] = []
    for tool in CHECK_ORDER:
        if not relevant & set(GATES_BY_TOOL[tool]):
            continue
        checks.append(_importable(tool) if tool in MODULES else _on_path(tool))
    return checks


def render(checks: list[Check]) -> str:
    lines = [f"gauntlet: {sys.argv[0]}", f"python:   {sys.executable}", ""]
    for check in checks:
        mark = "ok " if check.ok else "MISSING"
        lines.append(f"{mark:<8} {check.tool:<11} needed by {', '.join(check.gates)}")
        if not check.ok:
            lines.append(f"         {check.detail}")
    return "\n".join(lines)


def healthy(checks: list[Check]) -> bool:
    return all(check.ok for check in checks)
