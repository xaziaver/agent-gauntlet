"""The `gauntlet verdict` sub-app: a run's verdict record from the event log."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from gauntlet import events
from gauntlet import verdict as verdict_mod
from gauntlet.cli_support import fail, resolve_config

verdict_app = typer.Typer(no_args_is_help=True, help="A run's verdict as a committable record.")


def _no_verdict(lines: list[dict[str, Any]], run: str) -> str | None:
    """Why the run's lines are not a verdict, or None.

    A skip's `run.reused` line names the run whose lines are; a run with no
    `gate.finished` line (lock-rejected, or killed before its first gate) ran no gate.
    """
    reused = verdict_mod.deferred_to(lines)
    if reused is not None:
        return f"run {run} ran no gate: it reused run {reused}, whose lines are the verdict"
    if not any(line.get("kind") == events.GATE_FINISHED for line in lines):
        return f"run {run} ran no gate: no gate.finished line among its {len(lines)} line(s)"
    return None


@verdict_app.command("export")
def export(
    run: str = typer.Argument(..., help="The run id, as the log's `run` field names it"),
    path: Path = typer.Argument(..., help="Where to write the record"),
    log: Path | None = typer.Option(
        None, "--log", help="Read this copy of the log instead of the root's (no config needed)"
    ),
) -> None:
    """Write RUN's record from the event log: the shape `check --record` writes from a live run.

    Writes no event and takes no lock. A run that ran no gate has no verdict: a
    skip names the run it deferred to; either exits 1.
    """
    source = events.events_path(resolve_config()[0]) if log is None else log
    lines = verdict_mod.lines_of(events.read(source), run)
    if not lines:
        fail(f"run {run}: no lines in {source}")
    if (reason := _no_verdict(lines, run)) is not None:
        fail(reason)
    try:
        record = verdict_mod.from_lines(lines, run)
    except verdict_mod.ShortGateLineError as exc:
        fail(f"run {run}: {exc}")
    verdict_mod.write(path, record)
