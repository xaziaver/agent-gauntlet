"""Core gate contract. Every gate consumes a config + context and returns a GateResult."""

from __future__ import annotations

import fcntl
import functools
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn, Protocol

# Editor scratch files: Emacs lock (.#x.py) and autosave (#x.py#), backups (x.py~).
IGNORED_NAME_PREFIXES = (".#", "#")
TIMEOUT_RETURNCODE = 124  # conventional shell timeout code
MISSING_TOOL_RETURNCODE = 127  # conventional shell "command not found"
UNDECODABLE_RETURNCODE = 120  # program-defined; borrows no shell meaning

LOCK_FILE = Path(".gauntlet") / "run.lock"


class RunInProgressError(Exception):
    """Another gauntlet run holds the lock."""


@contextmanager
def exclusive_run(root: Path) -> Iterator[None]:
    """One gauntlet run per project at a time.

    Runs share .gauntlet/junit.xml, .gauntlet/coverage.json, and mutmut's
    mutants/ directory. Two overlapping runs read each other's half-written
    artifacts and report failures that are not real — which is worse than no
    gate, because it teaches everyone to re-run and shrug.
    """
    path = root / LOCK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise RunInProgressError("another gauntlet run is in progress") from exc
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def write_text_atomic(path: Path, text: str) -> None:
    """Temp file beside the target, then replace: no interruption leaves a partial file."""
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


class Interrupted(BaseException):
    """A signal landed mid-run. Unwind the finally blocks, then die with its status."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum

    @property
    def name(self) -> str:
        return signal.Signals(self.signum).name

    def die(self) -> NoReturn:
        """End the process as the signal would have: default disposition, re-delivered."""
        signal.signal(self.signum, signal.SIG_DFL)
        os.kill(os.getpid(), self.signum)
        raise SystemExit(128 + self.signum)  # the fallback that never runs


@contextmanager
def signals_raise() -> Iterator[None]:
    """SIGTERM and SIGHUP raise Interrupted on their first delivery, so a finally can
    restore what the run was writing; repeats while unwinding are ignored. Previous
    handlers come back on exit."""
    delivered: list[int] = []

    def handler(signum: int, _frame: FrameType | None) -> None:
        if delivered:
            return
        delivered.append(signum)
        raise Interrupted(signum)

    previous = {num: signal.signal(num, handler) for num in (signal.SIGTERM, signal.SIGHUP)}
    try:
        yield
    finally:
        for num, before in previous.items():
            signal.signal(num, before)


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
    # Passed because there was nothing to check — not the same as passing. A
    # gate with no input is silent under-enforcement unless it says so.
    vacuous: bool = False

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


FALLBACK_NOTE = (
    "no project .venv, no active virtualenv and no [project].python: this ran on "
    "Gauntlet's own interpreter, which does not carry the project's tooling"
)


def interpreter_note(ctx: GateContext) -> str:
    """Appended to a failure that ran on the fallback interpreter; empty otherwise.

    The message names the module; the cause is the missing venv. Nothing else in
    a gate's output says a fallback occurred.
    """
    return f" ({FALLBACK_NOTE})" if ctx.interpreter_fallback else ""


@dataclass
class GateContext:
    """Everything a gate needs to run."""

    project_root: Path
    src: Path
    tests: Path
    changed_files: list[Path] | None = None  # None = full run
    enabled_gates: list[str] = field(default_factory=list)
    verified_paths: list[str] = field(default_factory=list)
    python: str = field(default_factory=lambda: sys.executable)
    interpreter_fallback: bool = False  # `python` is Gauntlet's own, nothing else matched

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


def _failed(args: list[str], code: int, message: str) -> subprocess.CompletedProcess[str]:
    """The result `run_cmd` returns in place of an exception: no stdout, the reason on stderr."""
    return subprocess.CompletedProcess(args=args, returncode=code, stdout="", stderr=message)


def run_cmd(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Uniform subprocess wrapper: captured text output, no exception on nonzero exit.

    A timeout, missing executable or undecodable output is returned as a normal result (code
    124/127/120) rather than raised, so a hung tool becomes a gate error instead of a traceback in
    an agent hook.
    """
    try:
        return subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return _failed(
            args, TIMEOUT_RETURNCODE, f"timed out after {timeout}s: {' '.join(args[:3])}"
        )
    except (FileNotFoundError, PermissionError) as exc:
        return _failed(
            args,
            MISSING_TOOL_RETURNCODE,
            f"could not run {args[0]!r}: {exc}. Is it installed and on PATH?",
        )
    except UnicodeDecodeError as exc:
        byte, offset = exc.object[exc.start], exc.start
        why = f"byte 0x{byte:02x} at offset {offset}; stdout or stderr, the wrapper cannot tell"
        return _failed(args, UNDECODABLE_RETURNCODE, f"could not decode {args[0]!r} output: {why}")


def timed(fn: GateFn) -> GateFn:
    """Decorator: fills in GateResult.duration."""

    @functools.wraps(fn)
    def wrapper(ctx: GateContext, config: dict[str, Any]) -> GateResult:
        start = time.perf_counter()
        result = fn(ctx, config)
        object.__setattr__(result, "duration", round(time.perf_counter() - start, 3))
        return result

    return wrapper
