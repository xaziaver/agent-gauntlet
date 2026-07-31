"""Python acceptance adapter: pytest-bdd."""

from __future__ import annotations

import sys
from pathlib import Path

from gauntlet.adapters.base import RunResult
from gauntlet.gates.base import run_cmd

NO_TESTS_COLLECTED = 5


def run_acceptance(root: Path, steps: Path, timeout: int = 600) -> RunResult:
    """Execute the bound scenarios. Collecting nothing is a failure, not a pass."""
    proc = run_cmd(
        [sys.executable, "-m", "pytest", str(steps), "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=root,
        timeout=timeout,
    )
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode == NO_TESTS_COLLECTED:
        return RunResult(passed=False, output=f"no scenarios collected from {steps}")
    return RunResult(passed=proc.returncode == 0, output=output)
