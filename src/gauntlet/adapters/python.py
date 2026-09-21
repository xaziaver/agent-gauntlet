"""Python acceptance adapter: pytest-bdd."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from gauntlet.adapters.base import RunResult
from gauntlet.gates.base import MISSING_TOOL_RETURNCODE, run_cmd

NO_TESTS_COLLECTED = 5
VENV_CANDIDATES = (Path(".venv") / "bin" / "python", Path(".venv") / "Scripts" / "python.exe")

MUTMUT_RESULT_LINE = re.compile(r"^\s*(?P<name>[\w.]+):\s*(?P<status>\w+)\s*$")
SURVIVED = "survived"
MUTANT_SUFFIX = re.compile(r"__mutmut_\d+$")
MUTMUT_PROGRESS = re.compile(r"(?:^|\s)(\d+)/(\d+)(?:\s|$)")
MUTANTS_DIR = "mutants"  # mutmut's copy of the tree and its results, which it reuses
NOTHING_MATCHES = "nothing matches"  # mutmut's words when the filters name no mutant


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


def run_acceptance(
    root: Path, targets: Path | Sequence[Path], python: str, timeout: int = 600
) -> RunResult:
    """Execute the scenarios under the target(s). Collecting nothing is a failure, not a pass."""
    paths = [str(targets)] if isinstance(targets, Path) else [str(t) for t in targets]
    proc = run_cmd(
        [python, "-m", "pytest", *paths, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=root,
        timeout=timeout,
    )
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode == NO_TESTS_COLLECTED:
        return RunResult(passed=False, output=f"no scenarios collected from {', '.join(paths)}")
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


@dataclass(frozen=True)
class MutationRun:
    ok: bool
    total: int = 0
    survivors: list[str] = field(default_factory=list)
    error: str = ""


def parse_total(payload: str) -> int:
    """Total mutants, from mutmut's `N/M` progress fraction.

    Only the fraction is read, never the emoji counters beside it: those are for
    humans and will break the day an emoji changes.
    """
    return max((int(m.group(2)) for m in MUTMUT_PROGRESS.finditer(payload)), default=0)


def _clear_cache(root: Path) -> str | None:
    """Remove `mutants/` so the run is cold, or say why it could not be.

    mutmut reuses its per-function test selection across runs, keyed on test
    names and never their content, so a warm run can certify a suite whose
    assertions were removed. One that is already absent is the normal case.
    """
    cache = root / MUTANTS_DIR
    if not cache.is_symlink() and not cache.exists():
        return None
    try:
        shutil.rmtree(cache)
    except OSError as exc:
        return f"could not remove {MUTANTS_DIR}/ before the run: {exc}"
    return None


def _no_mutants(proc: subprocess.CompletedProcess[str], filters: list[str]) -> MutationRun:
    """A zero total is a broken configuration - unless filters were given and mutmut said
    they matched nothing, which is a run with nothing to do and is reported as one.
    Recognised by mutmut's words, read before the error is cut to 800 characters; if
    mutmut rewords them the result is today's tool failure, the closed direction."""
    if filters and NOTHING_MATCHES in proc.stdout + proc.stderr:
        return MutationRun(ok=True, total=0)
    return MutationRun(ok=False, error=(proc.stderr or proc.stdout).strip()[:800])


def run_mutmut(root: Path, python: str, filters: list[str], timeout: int) -> MutationRun:
    """Run mutmut cold and collect survivors.

    `mutmut results` lists only unkilled mutants, so the killed count is derived
    from the run total rather than by counting status lines. A cache Gauntlet
    could not clear is a tool failure, not a number: mutmut is not run.
    """
    not_cleared = _clear_cache(root)
    if not_cleared is not None:
        return MutationRun(ok=False, error=not_cleared)
    proc = run_cmd([python, "-m", "mutmut", "run", *filters], cwd=root, timeout=timeout)
    if proc.returncode == MISSING_TOOL_RETURNCODE:
        return MutationRun(ok=False, error=proc.stderr)
    total = parse_total(proc.stdout + proc.stderr)
    if total == 0:
        return _no_mutants(proc, filters)
    results = run_cmd([python, "-m", "mutmut", "results"], cwd=root, timeout=timeout)
    return MutationRun(
        ok=True, total=total, survivors=parse_results(results.stdout).get(SURVIVED, [])
    )


def show_mutant(root: Path, python: str, name: str, timeout: int = 60) -> tuple[str, str]:
    proc = run_cmd([python, "-m", "mutmut", "show", name], cwd=root, timeout=timeout)
    return parse_show(proc.stdout)
