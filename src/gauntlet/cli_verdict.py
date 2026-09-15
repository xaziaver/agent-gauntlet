"""The `gauntlet verdict` sub-app: a run's verdict record from the event log."""

from __future__ import annotations

from pathlib import Path

import typer

from gauntlet import events
from gauntlet import verdict as verdict_mod
from gauntlet.cli_support import fail, resolve_config

verdict_app = typer.Typer(no_args_is_help=True, help="A run's verdict as a committable record.")


@verdict_app.command("export")
def export(
    run: str = typer.Argument(..., help="The run id, as the log's `run` field names it"),
    path: Path = typer.Argument(..., help="Where to write the record"),
    log: Path | None = typer.Option(
        None, "--log", help="Read this copy of the log instead of the root's (no config needed)"
    ),
) -> None:
    """Write RUN's record from the event log: the shape `check --record` writes from a live run.

    Writes no event and takes no lock. A skip's `run.reused` line is not a verdict:
    export names the run it deferred to and exits 1.
    """
    source = events.events_path(resolve_config()[0]) if log is None else log
    lines = verdict_mod.lines_of(events.read(source), run)
    if not lines:
        fail(f"run {run}: no lines in {source}")
    reused = verdict_mod.deferred_to(lines)
    if reused is not None:
        fail(f"run {run} ran no gate: it reused run {reused}, whose lines are the verdict")
    verdict_mod.write(path, verdict_mod.from_lines(lines, run))
