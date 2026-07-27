"""Core gate contract. Every gate consumes a config + context and returns a GateResult."""

from __future__ import annotations

import functools
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

# Editor scratch files: Emacs lock (.#x.py) and autosave (#x.py#), backups (x.py~).
IGNORED_NAME_PREFIXES = (".#", "#")


@dataclass(frozen=True)
class Diagnostic:
    file: str
    message: str
    symbol: str | None = None
    line: int | None = None
    value: float | None = None


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    threshold: Any
    actual: Any
    diagnostics: list[Diagnostic] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None  # tool crashed, vs. a legitimate gate failure

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_analyzable(path: Path) -> bool:
    """A real Python file we should look at.

    Excludes editor lock/backup artifacts and anything that vanished mid-run:
    agents create and delete files constantly, and a gate must never crash on that.
    """
    if path.suffix != ".py" or path.name.startswith(IGNORED_NAME_PREFIXES):
        return False
    return path.is_file()


@dataclass
class GateContext:
    """Everything a gate needs to run."""

    project_root: Path
    src: Path
    tests: Path
    changed_files: list[Path] | None = None  # None = full run
    enabled_gates: list[str] = field(default_factory=list)

    def python_files(self) -> list[Path]:
        """Analyzable Python files under src/, narrowed to changed files with --changed."""
        candidates = self.src.rglob("*.py") if self.changed_files is None else self.changed_files
        return sorted(f for f in candidates if is_analyzable(f) and f.is_relative_to(self.src))

    def tool_targets(self) -> list[str]:
        """Paths to hand an external tool: the whole src tree, or just the changed files."""
        if self.changed_files is None:
            return [str(self.src)]
        return [str(f) for f in self.python_files()]


GateFn = Callable[[GateContext, dict[str, Any]], GateResult]


class Gate(Protocol):
    name: str

    def run(self, ctx: GateContext, config: dict[str, Any]) -> GateResult: ...


def run_cmd(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Uniform subprocess wrapper: captured text output, no exception on nonzero exit."""
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def timed(fn: GateFn) -> GateFn:
    """Decorator: fills in GateResult.duration."""

    @functools.wraps(fn)
    def wrapper(ctx: GateContext, config: dict[str, Any]) -> GateResult:
        start = time.perf_counter()
        result = fn(ctx, config)
        object.__setattr__(result, "duration", round(time.perf_counter() - start, 3))
        return result

    return wrapper
