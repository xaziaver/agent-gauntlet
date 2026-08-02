"""Environment checks: is every enabled gate actually able to run?

Hooks fail open by design — a broken Gauntlet exits 1, Claude Code shrugs, and
enforcement silently disappears while the session looks normal. This is the
command that makes that state visible.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CHECK_ORDER = (
    "git",
    "ruff",
    "mypy",
    "radon",
    "pytest",
    "pytest-cov",
    "pytest-bdd",
    "mutmut",
    "jscpd",
)

# Which gates need which tool. Gates absent here need only the standard library.
GATES_BY_TOOL = {
    "git": ("--changed",),
    "ruff": ("static",),
    "mypy": ("static",),
    "radon": ("complexity", "crap"),
    "pytest": ("tests",),
    "pytest-cov": ("coverage", "crap"),
    "pytest-bdd": ("acceptance",),
    "mutmut": ("mutation",),
    "jscpd": ("duplication",),
}

PROJECT_MODULES = {
    "pytest": "pytest",
    "pytest-cov": "pytest_cov",
    "pytest-bdd": "pytest_bdd",
    "mutmut": "mutmut",
}

OWN_MODULES = {"mypy": "mypy"}


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


def _importable_by(tool: str, module: str, python: str) -> Check:
    proc = subprocess.run(
        [python, "-c", f"import {module}"], capture_output=True, text=True, check=False
    )
    detail = (
        f"importable by {python}"
        if proc.returncode == 0
        else (f"module {module!r} not importable by {python}")
    )
    return Check(tool=tool, ok=proc.returncode == 0, detail=detail)


def _check_for(tool: str, python: str) -> Check:
    if tool in PROJECT_MODULES:
        return _importable_by(tool, PROJECT_MODULES[tool], python)
    if tool in OWN_MODULES:
        return _importable_by(tool, OWN_MODULES[tool], sys.executable)
    return _on_path(tool)


def run_checks(enabled_gates: list[str], python: str | None = None) -> list[Check]:
    """One check per tool any enabled gate (or --changed) depends on."""
    resolved = python or sys.executable
    relevant = set(enabled_gates) | {"--changed"}
    return [
        _check_for(tool, resolved) for tool in CHECK_ORDER if relevant & set(GATES_BY_TOOL[tool])
    ]


def _check_lines(check: Check) -> list[str]:
    mark = "ok " if check.ok else "MISSING"
    lines = [f"{mark:<8} {check.tool:<11} needed by {', '.join(check.gates)}"]
    if not check.ok:
        lines.append(f"         {check.detail}")
    return lines


def _header(python: str | None) -> list[str]:
    return [
        f"gauntlet: {sys.argv[0]}",
        f"gauntlet python: {sys.executable}",
        f"project python:  {python or sys.executable}",
        "",
    ]


def render(
    checks: list[Check], python: str | None = None, warnings: list[str] | None = None
) -> str:
    lines = _header(python)
    for check in checks:
        lines.extend(_check_lines(check))
    lines.extend(f"\nWARNING  {warning}" for warning in warnings or [])
    return "\n".join(lines)


def healthy(checks: list[Check]) -> bool:
    return all(check.ok for check in checks)


def mutants_dir_warning(root: Path, enabled_gates: list[str]) -> str | None:
    """mutmut's ./mutants copy collides with the project's own test collection."""
    if "mutation" not in enabled_gates or not (root / "mutants").is_dir():
        return None
    config = root / "pyproject.toml"
    text = config.read_text(encoding="utf-8") if config.is_file() else ""
    if "--ignore=mutants" in text or "--ignore ./mutants" in text:
        return None
    return (
        "./mutants exists (created by mutmut) and pytest is not ignoring it. "
        'Add addopts = "--ignore=mutants" under [tool.pytest.ini_options], '
        "and put mutants/ in .gitignore."
    )


def warnings_for(root: Path, enabled_gates: list[str]) -> list[str]:
    """Advisory environment problems: real, but not a missing tool."""
    found = [mutants_dir_warning(root, enabled_gates)]
    return [w for w in found if w is not None]
