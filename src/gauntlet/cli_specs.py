"""The `gauntlet spec` sub-app."""

from __future__ import annotations

from pathlib import Path

import typer

from gauntlet import locking, registry
from gauntlet import specs as specs_mod
from gauntlet.cli_support import fail, resolve_config

spec_app = typer.Typer(no_args_is_help=True, help="Manage acceptance specifications.")


@spec_app.command("approve")
def spec_approve(paths: list[Path]) -> None:
    """Approve one or more feature files. The deliberate human review step."""
    root, _ = resolve_config()
    try:
        updated = specs_mod.approve(root, paths)
    except FileNotFoundError as exc:
        fail(f"no such spec: {exc}")
    registry.save(updated, locking.lock_path(root))
    for path in paths:
        typer.echo(f"approved  {specs_mod.key_for(root, path)}")


@spec_app.command("list")
def spec_list() -> None:
    """Show every discovered spec and whether it is approved."""
    root, cfg = resolve_config()
    features_dir = str(cfg.gates.get("acceptance", {}).get("features", "features/"))
    approved = registry.load(locking.lock_path(root))
    for line in specs_mod.status_lines(root, features_dir, approved):
        typer.echo(line)
