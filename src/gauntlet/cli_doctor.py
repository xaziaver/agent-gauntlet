"""The `gauntlet doctor` and `gauntlet version` commands: what is installed here?"""

from __future__ import annotations

import typer

from gauntlet import __version__
from gauntlet import doctor as doctor_mod
from gauntlet.adapters import python as python_adapter
from gauntlet.cli_support import EXIT_CONFIG_ERROR, EXIT_OK, resolve_config

doctor_app = typer.Typer(no_args_is_help=True, help="Check this environment.")


@doctor_app.command("doctor")
def doctor() -> None:
    """Check that every enabled gate's tooling is present in THIS environment.

    Run it with the same command your hooks use (bare `gauntlet doctor`, not
    `uv run gauntlet doctor`) — a broken hook environment fails open silently,
    and this is how you find out.
    """
    root, cfg = resolve_config()
    project_python = python_adapter.interpreter(root, cfg.python)
    checks = doctor_mod.run_checks(cfg.enabled_gates, project_python)
    warnings = doctor_mod.warnings_for(root, cfg.src, cfg.enabled_gates, cfg.disabled_gates)
    typer.echo(doctor_mod.render(checks, project_python, warnings))
    raise typer.Exit(code=EXIT_OK if doctor_mod.healthy(checks) else EXIT_CONFIG_ERROR)


@doctor_app.command("version")
def version() -> None:
    """Print the gauntlet version."""
    typer.echo(__version__)
