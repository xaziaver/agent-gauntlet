"""Python acceptance adapter: pytest-bdd."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from gauntlet.adapters.base import RunResult
from gauntlet.gates.base import MISSING_TOOL_RETURNCODE, run_cmd

NO_TESTS_COLLECTED = 5
VENV_CANDIDATES = (Path(".venv") / "bin" / "python", Path(".venv") / "Scripts" / "python.exe")

MUTMUT_RESULT_LINE = re.compile(r"^\s*(?P<name>[\w.]+):\s*(?P<status>\w+)\s*$")
SURVIVED = "survived"
MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")


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


@dataclass(frozen=True)
class CodeMutant:
    """One mutmut mutant, identified structurally rather than by mutmut's ID.

    mutmut names mutants positionally (`x_calc__mutmut_63`), so the number shifts
    whenever the function changes. Identity here is the module, the function, and
    the source line being altered — which survives unrelated edits.
    """

    name: str
    module: str
    function: str
    removed: str
    added: str

    @property
    def locator(self) -> str:
        return f"{self.module}|{self.function}|{self.removed}|{self.added}"

    @property
    def signature(self) -> str:
        return f"{self.removed}->{self.added}"

    @property
    def description(self) -> str:
        return f"{self.module}.{self.function}: {self.removed} -> {self.added}"


def parse_mutant_name(name: str) -> tuple[str, str]:
    """`pkg.mod.x_calculate__mutmut_63` -> ("pkg.mod", "calculate")."""
    module, _, tail = name.rpartition(".")
    function = MUTANT_SUFFIX.sub("", tail)
    return module, function.removeprefix("x_")


def parse_results(payload: str) -> dict[str, list[str]]:
    """`mutmut results` -> {status: [mutant names]}.

    Only the `name: status` lines are parsed. The spinner line with its emoji
    counters is for humans and will break the day an emoji changes.
    """
    buckets: dict[str, list[str]] = {}
    for line in payload.splitlines():
        match = MUTMUT_RESULT_LINE.match(line)
        if match:
            buckets.setdefault(match["status"], []).append(match["name"])
    return buckets


def _diff_lines(payload: str, marker: str) -> list[str]:
    header = marker * 3
    return [
        line[1:].strip()
        for line in payload.splitlines()
        if line.startswith(marker) and not line.startswith(header)
    ]


def parse_show(payload: str) -> tuple[str, str]:
    """A unified diff from `mutmut show` -> (first removed line, first added line)."""
    removed = _diff_lines(payload, "-")
    added = _diff_lines(payload, "+")
    return (removed[0] if removed else "", added[0] if added else "")


def _dotted(src: Path, path: Path) -> str:
    parts = [p for p in path.relative_to(src).with_suffix("").parts if p != "__init__"]
    return ".".join(parts)


def _module_name(src: Path, path: Path) -> str | None:
    if path.suffix != ".py" or not path.is_relative_to(src):
        return None
    dotted = _dotted(src, path)
    return f"{dotted}*" if dotted else None


def module_filter(src: Path, changed: list[Path]) -> list[str]:
    """Changed files -> mutmut name filters like `pkg.mod*`.

    mutmut 3 scopes by mutant name, not by path, so changed-file scope means
    translating paths into dotted module names.
    """
    names = (_module_name(src, path) for path in changed)
    return sorted({name for name in names if name is not None})


def run_mutmut(root: Path, python: str, filters: list[str], timeout: int) -> RunResult:
    """Run mutmut, then collect results. Its exit code reflects survivors, not failure."""
    proc = run_cmd([python, "-m", "mutmut", "run", *filters], cwd=root, timeout=timeout)
    if proc.returncode == MISSING_TOOL_RETURNCODE:
        return RunResult(passed=False, output=proc.stderr)
    results = run_cmd([python, "-m", "mutmut", "results"], cwd=root, timeout=timeout)
    return RunResult(passed=True, output=results.stdout)


def show_mutant(root: Path, python: str, name: str, timeout: int = 60) -> tuple[str, str]:
    proc = run_cmd([python, "-m", "mutmut", "show", name], cwd=root, timeout=timeout)
    return parse_show(proc.stdout)
