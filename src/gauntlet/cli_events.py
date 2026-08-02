"""The `gauntlet events` command: what a live dashboard would render."""

from __future__ import annotations

import json

import typer

from gauntlet import events
from gauntlet.cli_support import EXIT_OK, resolve_config

ENVELOPE = ("v", "at", "run", "kind")

events_app = typer.Typer(no_args_is_help=False, help="Inspect the event log.")


def _detail(item: dict[str, object]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(item.items()) if k not in ENVELOPE)


@events_app.callback(invoke_without_command=True)
def show(
    limit: int = typer.Option(20, "--limit", help="Most recent N events; 0 for all"),
    json_out: bool = typer.Option(False, "--json", help="Raw JSONL"),
) -> None:
    """Show recent activity: runs, gate results, approvals, and escalations."""
    root, _ = resolve_config()
    items = events.read(events.events_path(root), limit)
    for item in items:
        if json_out:
            typer.echo(json.dumps(item, sort_keys=True))
        else:
            typer.echo(f"{item.get('at', '?')}  {item.get('kind', '?'):<18} {_detail(item)}")
    raise typer.Exit(code=EXIT_OK)
