"""External driver for agents that cannot be hooked.

Basic LLM CLIs will neither self-invoke `gauntlet check` nor be interrupted by
lifecycle hooks, so the loop runs from outside: agent -> gates -> feed the
failure report back as the next prompt -> repeat, to a cap. Deliberately dumb:
no conversation state, no roles, no handoffs. The moment it grows those it is
multi-agent orchestration, which is out of scope by design.

Contract for the agent command: read the prompt on stdin, edit files in the
working directory, exit. `claude -p`, `aider --message-file /dev/stdin`, and
anything similar qualifies.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gauntlet import config as config_mod
from gauntlet import events, report, runner

DEFAULT_MAX_ITERATIONS = 5
DEFAULT_AGENT_TIMEOUT = 1800
MISSING_AGENT_RETURNCODE = 127

FIRST_TEMPLATE = """\
{task}

This project is gated by Gauntlet. When you believe you are done, your work will
be checked by deterministic quality gates. Write clean, tested code.
"""

REMEDIATION_TEMPLATE = """\
Your previous attempt at this task did not pass the quality gates.

The task, unchanged:
{task}

The gate report (JSON). Each diagnostic names a file, a symbol, a line, and the
remedy. Fix exactly what the diagnostics describe — do not weaken thresholds,
do not delete tests, do not restate the code that already passes:
{report}
"""


@dataclass(frozen=True)
class LoopSettings:
    command: str
    task: str
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout: int = DEFAULT_AGENT_TIMEOUT


class LoopError(Exception):
    """The loop cannot run: bad task input or a missing agent command."""


def first_prompt(task: str) -> str:
    return FIRST_TEMPLATE.format(task=task.strip())


def remediation_prompt(task: str, report_json: str) -> str:
    return REMEDIATION_TEMPLATE.format(task=task.strip(), report=report_json)


def read_task(task: str, task_file: Path | None) -> str:
    if task and task_file is not None:
        raise LoopError("provide --task or --task-file, not both.")
    if task_file is not None:
        if not task_file.is_file():
            raise LoopError(f"task file not found: {task_file}")
        return task_file.read_text(encoding="utf-8")
    if task:
        return task
    raise LoopError("provide the task with --task or --task-file.")


def _failed(args: list[str], code: int, stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=code, stdout="", stderr=stderr)


def run_agent(
    command: str, prompt: str, cwd: Path, timeout: int = DEFAULT_AGENT_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """One agent invocation: prompt on stdin, captured output, no exceptions."""
    args = shlex.split(command)
    try:
        return subprocess.run(
            args,
            input=prompt,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failed(args, 124, f"agent timed out after {timeout}s")
    except (FileNotFoundError, PermissionError) as exc:
        return _failed(args, MISSING_AGENT_RETURNCODE, f"could not run {args[0]!r}: {exc}")


def _turn(command: str, prompt: str, cwd: Path, timeout: int, echo: Callable[..., None]) -> None:
    """One agent turn. A missing agent command is fatal; a nonzero exit is not —
    the agent may have edited files before dying, and the gates will judge those."""
    proc = run_agent(command, prompt, cwd, timeout)
    if proc.returncode == MISSING_AGENT_RETURNCODE:
        raise LoopError(proc.stderr)
    if proc.stdout.strip():
        echo(proc.stdout)
    if proc.returncode != 0:
        echo(f"agent exited {proc.returncode}: {proc.stderr.strip()[:500]}", err=True)


def drive(
    root: Path,
    cfg: config_mod.Config,
    selected: list[str],
    settings: LoopSettings,
    echo: Callable[..., None],
    log: events.Log | None = None,
) -> tuple[bool, str]:
    sink = log or events.disabled()
    prompt = first_prompt(settings.task)
    last_report = ""
    for iteration in range(1, settings.max_iterations + 1):
        sink.emit(events.AGENT_ITERATION, iteration=iteration, max=settings.max_iterations)
        echo(f"=== gauntlet loop: iteration {iteration}/{settings.max_iterations} ===")
        _turn(settings.command, prompt, root, settings.timeout, echo)
        results = runner.run_full_gauntlet(root, cfg, selected, sink)
        if report.passed(results):
            echo(f"GAUNTLET PASSED after {iteration} iteration(s)")
            return True, ""
        last_report = report.to_json(results, cfg.max_diagnostics)
        prompt = remediation_prompt(settings.task, last_report)
    return False, last_report
