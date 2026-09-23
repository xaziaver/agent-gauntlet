"""The `gauntlet status` command: where does this project stand?"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from gauntlet import config as config_mod
from gauntlet import events, registry, runner, status_render
from gauntlet import status as status_mod
from gauntlet.cli_support import EXIT_OK, fail, resolve_config, select_gates
from gauntlet.gates.base import GateResult

status_app = typer.Typer(no_args_is_help=False, help="Project status at a glance.")


def _run_now(root: Path, cfg: config_mod.Config) -> list[GateResult]:
    """`--run`: every enabled gate now, logged as a run, before the report."""
    selected = select_gates("", cfg)
    ctx = runner.build_context(root, cfg, selected, changed=False)
    return runner.run_gates(ctx, cfg, selected, fail_fast=False, log=events.Log(root))


@status_app.callback(invoke_without_command=True)
def show(
    run: bool = typer.Option(
        False, "--run", help="Run the gates now instead of reporting the last known state"
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable status"),
) -> None:
    """Gates, pending approvals, and recent activity.

    Exits 0 whatever the gates say: this is a report, not a gate. `gauntlet check`
    is the gate. A ledger the tool cannot read is the one config error, exit 1.
    """
    root, cfg = resolve_config()
    results = _run_now(root, cfg) if run else []
    try:
        current = status_mod.collect(root, cfg, results)
    except registry.RegistryError as exc:
        fail(str(exc))
    typer.echo(
        json.dumps(current.to_dict(), indent=2, default=str)
        if json_out
        else status_render.render(current)
    )
    raise typer.Exit(code=EXIT_OK)
