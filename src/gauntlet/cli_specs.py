"""The `gauntlet spec` sub-app."""

from __future__ import annotations

from pathlib import Path

import typer

from gauntlet import locking, registry
from gauntlet import specs as specs_mod
from gauntlet.cli_support import fail, load_registry, resolve_config

spec_app = typer.Typer(no_args_is_help=True, help="Manage acceptance specifications.")


def _keys(root: Path, paths: list[Path]) -> list[str]:
    """Each path's ledger key; a path outside the project is refused, not a traceback."""
    keys = []
    for path in paths:
        try:
            keys.append(specs_mod.key_for(root, path))
        except ValueError:
            fail(f"{path} is outside the project")
    return keys


@spec_app.command("approve")
def spec_approve(paths: list[Path]) -> None:
    """Approve one or more feature files. The deliberate human review step."""
    root, _ = resolve_config()
    keys = _keys(root, paths)
    try:
        updated = specs_mod.approve(root, paths)
    except FileNotFoundError as exc:
        fail(f"no such spec: {exc}")
    except registry.RegistryError as exc:
        fail(str(exc))
    registry.save(updated, locking.lock_path(root))
    for key in keys:
        typer.echo(f"approved  {key}")


def _fate(item: specs_mod.Unapproved) -> str:
    if not item.mutants:
        return ""
    if item.exists:
        return f" ({item.mutants} mutant approval(s) kept)"
    return f" ({item.mutants} mutant approval(s) removed with it: the spec no longer exists)"


@spec_app.command("unapprove")
def spec_unapprove(paths: list[Path]) -> None:
    """Withdraw the approval of one or more specs. A spec that no longer exists
    takes its mutant approvals with it; one that exists keeps them."""
    root, _ = resolve_config()
    _keys(root, paths)
    try:
        updated, done = specs_mod.unapprove(root, paths)
    except (specs_mod.SpecError, registry.RegistryError) as exc:
        fail(str(exc))
    registry.save(updated, locking.lock_path(root))
    for item in done:
        typer.echo(f"unapproved  {item.key}{_fate(item)}")


@spec_app.command("rename")
def spec_rename(old: Path, new: Path) -> None:
    """Carry every approval of a spec after a file that has moved: `git mv` first."""
    root, _ = resolve_config()
    _keys(root, [old, new])
    try:
        updated, moved = specs_mod.rename(root, old, new)
    except (specs_mod.SpecError, registry.RegistryError) as exc:
        fail(str(exc))
    registry.save(updated, locking.lock_path(root))
    typer.echo(
        f"moved  {moved.old} -> {moved.new} ({moved.mutants} mutant approval(s) moved with it)"
    )
    if moved.differs:
        typer.echo(
            f"  {moved.new} differs from the approved content: "
            f"`gauntlet spec approve {moved.new}` re-approves it"
        )


@spec_app.command("list")
def spec_list() -> None:
    """Show every discovered spec and whether it is approved."""
    root, cfg = resolve_config()
    features_dir = str(cfg.gates.get("acceptance", {}).get("features", "features/"))
    approved = load_registry(locking.lock_path(root))
    for line in specs_mod.status_lines(root, features_dir, approved):
        typer.echo(line)
