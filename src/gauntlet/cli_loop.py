"""The `gauntlet loop` command: drive an agent that cannot be hooked."""

from __future__ import annotations

from pathlib import Path

import typer

from gauntlet import events
from gauntlet import loop as loop_mod
from gauntlet.cli_support import EXIT_GATE_FAILURE, EXIT_OK, fail, resolve_config, select_gates

loop_app = typer.Typer(no_args_is_help=False, help="Drive an un-hookable agent.")


def _settings(
    cmd: str, task: str, task_file: Path | None, max_iterations: int, timeout: int
) -> loop_mod.LoopSettings:
    return loop_mod.LoopSettings(
        command=cmd,
        task=loop_mod.read_task(task, task_file),  # may raise LoopError; caller catches
        max_iterations=max_iterations,
        timeout=timeout,
    )


@loop_app.callback(invoke_without_command=True)
def loop(
    cmd: str = typer.Option(
        ..., "--cmd", help='Agent command reading a prompt on stdin, e.g. "claude -p"'
    ),
    task: str = typer.Option("", help="The task prompt"),
    task_file: Path | None = typer.Option(None, help="Read the task prompt from a file"),
    max_iterations: int = typer.Option(loop_mod.DEFAULT_MAX_ITERATIONS),
    agent_timeout: int = typer.Option(loop_mod.DEFAULT_AGENT_TIMEOUT),
) -> None:
    """Run the agent, run the gates, feed failures back, repeat to a cap."""
    root, cfg = resolve_config()
    log = events.Log(root)
    try:
        settings = _settings(cmd, task, task_file, max_iterations, agent_timeout)
        passed, last_report = loop_mod.drive(
            root, cfg, select_gates("", cfg), settings, typer.echo, log
        )
    except loop_mod.LoopError as exc:
        fail(str(exc))
    if passed:
        raise typer.Exit(code=EXIT_OK)
    typer.echo(last_report, err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)
