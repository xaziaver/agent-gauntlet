"""The `gauntlet status` command: where does this project stand?"""

from __future__ import annotations

import json

import typer

from gauntlet import events, runner, status_render
from gauntlet import status as status_mod
from gauntlet.cli_support import EXIT_OK, resolve_config, select_gates

status_app = typer.Typer(no_args_is_help=False, help="Project status at a glance.")


@status_app.callback(invoke_without_command=True)
def show(
    run: bool = typer.Option(
        False, "--run", help="Run the gates now instead of reporting the last known state"
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable status"),
) -> None:
    """Gates, pending approvals, and recent activity.

    Always exits 0: this is a report, not a gate. `gauntlet check` is the gate.
    """
    root, cfg = resolve_config()
    results = []
    if run:
        selected = select_gates("", cfg)
        log = events.Log(root)
        ctx = runner.build_context(root, cfg, selected, changed=False)
        results = runner.run_gates(ctx, cfg, selected, fail_fast=False, log=log)
    current = status_mod.collect(root, cfg, results)
    typer.echo(
        json.dumps(current.to_dict(), indent=2, default=str)
        if json_out
        else status_render.render(current)
    )
    raise typer.Exit(code=EXIT_OK)
