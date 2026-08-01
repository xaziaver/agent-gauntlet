"""Python acceptance adapter: pytest-bdd."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from gauntlet.adapters.base import RunResult
from gauntlet.gates.base import run_cmd

NO_TESTS_COLLECTED = 5
VENV_CANDIDATES = (Path(".venv") / "bin" / "python", Path(".venv") / "Scripts" / "python.exe")


def interpreter(root: Path, configured: str | None = None) -> str:
    """The interpreter that has the PROJECT's dependencies installed.

    Not sys.executable: when Gauntlet runs as an agent hook, that is Gauntlet's
    own venv, which knows nothing about the project's libraries.

    Symlinks are deliberately NOT resolved. A venv's bin/python is a symlink to
    the base interpreter, and resolving it yields an interpreter without the
    venv's site-packages — the venv silently stops applying. Order is explicit
    config, then a local .venv, then an active virtualenv, then us.
    """
    if configured:
        candidate = Path(configured)
        return str(candidate if candidate.is_absolute() else root / candidate)
    local = _venv_python(root)
    if local is not None:
        return local
    active = os.environ.get("VIRTUAL_ENV")
    if active:
        found = _bin_python(Path(active))
        if found is not None:
            return found
    return sys.executable


def _bin_python(venv: Path) -> str | None:
    """The interpreter inside a venv directory, unresolved."""
    for relative in (Path("bin") / "python", Path("Scripts") / "python.exe"):
        candidate = venv / relative
        if candidate.exists():
            return str(candidate)
    return None


def _venv_python(root: Path) -> str | None:
    return _bin_python(root / ".venv")


def run_acceptance(root: Path, steps: Path, python: str, timeout: int = 600) -> RunResult:
    """Execute the bound scenarios. Collecting nothing is a failure, not a pass."""
    proc = run_cmd(
        [python, "-m", "pytest", str(steps), "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=root,
        timeout=timeout,
    )
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode == NO_TESTS_COLLECTED:
        return RunResult(passed=False, output=f"no scenarios collected from {steps}")
    return RunResult(passed=proc.returncode == 0, output=output)
