"""The `gauntlet mutant` sub-app: classify surviving acceptance mutants."""

from __future__ import annotations

from pathlib import Path

import typer

from gauntlet import config as config_mod
from gauntlet import locking, registry, runner, specs
from gauntlet import mutants as mutants_mod
from gauntlet.acceptance.mutation import Mutant
from gauntlet.cli_support import EXIT_OK, fail, resolve_config
from gauntlet.gates import acceptance

mutant_app = typer.Typer(no_args_is_help=True, help="Review surviving mutants.")


def _feature_key(root: Path, feature: Path) -> str:
    if not feature.is_file():
        fail(f"no such feature file: {feature}")
    return specs.key_for(root, feature)


@mutant_app.command("list")
def mutant_list() -> None:
    """Show every reviewed-equivalent mutant and the reason it was accepted."""
    root, _ = resolve_config()
    approved = registry.load(locking.lock_path(root))
    scoped = registry.in_namespace(approved, mutants_mod.MUTANT_NAMESPACE)
    for key, entry in sorted(scoped.entries.items()):
        reason = entry.reason or "(no reason recorded)"
        typer.echo(f"{registry.bare(key)}\n    {reason}  [{entry.reviewer or 'unknown'}]")
    raise typer.Exit(code=EXIT_OK)


def _acceptance_config(cfg: config_mod.Config) -> dict[str, object]:
    return cfg.gates.get("acceptance", {})


def _current_survivors(
    root: Path, cfg: config_mod.Config, feature: Path, scenario: str
) -> list[Mutant]:
    """Re-run the mutation loop for one feature, through the gate's own helper."""
    config = _acceptance_config(cfg)
    ctx = runner.build_context(root, cfg, cfg.enabled_gates, changed=False)
    steps = root / str(config.get("steps", "tests/steps"))
    survivors = acceptance.survivors_for(ctx, config, feature, steps)
    if scenario:
        return [m for m in survivors if m.scenario == scenario]
    return survivors


@mutant_app.command("approve")
def mutant_approve(
    feature: Path = typer.Argument(..., help="The feature file the survivors came from"),
    reason: str = typer.Option(..., "--reason", help="Why these cannot change behavior"),
    reviewer: str = typer.Option("", "--reviewer", help="Who judged them"),
    scenario: str = typer.Option("", help="Only survivors from this scenario"),
) -> None:
    """Record that the current survivors are equivalent mutants.

    This is a judgment about the domain, not a way to silence a gate: an
    equivalent mutant is one the specification cannot distinguish. The reason is
    required because it is what a future reviewer needs.
    """
    root, cfg = resolve_config()
    key = _feature_key(root, feature)
    survivors = _current_survivors(root, cfg, feature, scenario)
    if not survivors:
        typer.echo("no surviving mutants to approve")
        raise typer.Exit(code=EXIT_OK)
    updated = mutants_mod.approve(root, key, survivors, reason=reason, reviewer=reviewer)
    registry.save(updated, locking.lock_path(root))
    for mutant in survivors:
        typer.echo(f"approved  {mutant.signature}  in {mutant.scenario!r}")


@mutant_app.command("prune")
def mutant_prune(
    feature: Path = typer.Argument(..., help="The feature file to prune approvals for"),
) -> None:
    """Drop approvals for mutants that no longer survive.

    An assertion got sharper and now kills what a human once judged equivalent.
    The judgment is stale, not wrong — remove it so the ledger stays honest.
    """
    root, cfg = resolve_config()
    key = _feature_key(root, feature)
    approved = registry.load(locking.lock_path(root))
    verdict = mutants_mod.classify(approved, key, _current_survivors(root, cfg, feature, ""))
    if not verdict.stale:
        typer.echo("no stale approvals")
        raise typer.Exit(code=EXIT_OK)
    for stale_key in verdict.stale:
        approved = registry.revoke(
            approved, registry.namespaced(mutants_mod.MUTANT_NAMESPACE, stale_key)
        )
        typer.echo(f"pruned  {stale_key}")
    registry.save(approved, locking.lock_path(root))
