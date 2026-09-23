"""The `gauntlet mutant` sub-app: classify surviving acceptance mutants."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn, TypeVar

import typer

from gauntlet import config as config_mod
from gauntlet import locking, registry, runner, specs
from gauntlet import mutants as mutants_mod
from gauntlet.acceptance import gherkin, mutation
from gauntlet.acceptance.mutation import Mutant
from gauntlet.adapters.python import CodeMutant
from gauntlet.cli_support import EXIT_OK, fail, load_registry, resolve_config
from gauntlet.gates import acceptance, base
from gauntlet.gates.mutation import SUBJECT, MutmutError, survivors_for

mutant_app = typer.Typer(no_args_is_help=True, help="Review surviving mutants.")

M = TypeVar("M", bound=mutants_mod.MutantLike)


def _classify(
    approved: registry.Registry, subject_key: str, survivors: list[M]
) -> mutants_mod.Classification[M]:
    return mutants_mod.classify(approved, subject_key, survivors)


def _record(
    root: Path, subject_key: str, survivors: list[M], reason: str, reviewer: str
) -> NoReturn:
    """The approval ceremony, shared by acceptance and code mutants."""
    if not survivors:
        typer.echo("no surviving mutants to approve")
        raise typer.Exit(code=EXIT_OK)
    updated = mutants_mod.approve(root, subject_key, survivors, reason=reason, reviewer=reviewer)
    registry.save(updated, locking.lock_path(root))
    for mutant in survivors:
        typer.echo(f"approved  {mutant.description}")
    raise typer.Exit(code=EXIT_OK)


def _prune_stale(root: Path, approved: registry.Registry, stale: list[str]) -> NoReturn:
    """Drop approvals whose mutants no longer survive."""
    if not stale:
        typer.echo("no stale approvals")
        raise typer.Exit(code=EXIT_OK)
    for stale_key in stale:
        approved = registry.revoke(
            approved, registry.namespaced(mutants_mod.MUTANT_NAMESPACE, stale_key)
        )
        typer.echo(f"pruned  {stale_key}")
    registry.save(approved, locking.lock_path(root))
    raise typer.Exit(code=EXIT_OK)


def _feature_key(root: Path, feature: Path) -> str:
    if not feature.is_file():
        fail(f"no such feature file: {feature}")
    return specs.key_for(root, feature)


def _acceptance_config(cfg: config_mod.Config) -> dict[str, object]:
    return cfg.gates.get("acceptance", {})


def _current_survivors(
    root: Path, cfg: config_mod.Config, feature: Path, scenario: str
) -> list[Mutant]:
    """Re-run the mutation loop for one feature, through the gate's own helper."""
    config = _acceptance_config(cfg)
    ctx = runner.build_context(root, cfg, cfg.enabled_gates, changed=False)
    steps = root / str(config.get("steps", "tests/steps"))
    try:
        survivors = acceptance.survivors_for(ctx, config, feature, steps)
    except base.Interrupted as exc:
        exc.die()  # the gate's finally has already restored the spec
    except acceptance.NotMeasuredError as exc:
        fail(str(exc))  # the gate's sentence, and nothing written
    if scenario:
        return [m for m in survivors if m.scenario == scenario]
    return survivors


def _current_code_survivors(root: Path, cfg: config_mod.Config) -> list[CodeMutant]:
    """Whole-tree survivors, through the gate's own entry point."""
    config = cfg.gates.get("mutation", {})
    ctx = runner.build_context(root, cfg, cfg.enabled_gates, changed=False)
    try:
        return survivors_for(root, ctx.python, [], int(config.get("timeout", 1800)))
    except MutmutError as exc:
        fail(str(exc)[:500])


@mutant_app.command("approve")
def mutant_approve(
    feature: Path = typer.Argument(..., help="The feature file the survivors came from"),
    reason: str = typer.Option(..., "--reason", help="Why these cannot change behavior"),
    reviewer: str = typer.Option("", "--reviewer", help="Who judged them"),
    scenario: str = typer.Option("", help="Only survivors from this scenario"),
) -> None:
    """Record that the current acceptance survivors are equivalent mutants.

    This is a judgment about the domain, not a way to silence a gate: an
    equivalent mutant is one the specification cannot distinguish. The reason is
    required because it is what a future reviewer needs.
    """
    root, cfg = resolve_config()
    key = _feature_key(root, feature)
    # A ledger the tool cannot read is refused here, before the mutation run, not after it.
    load_registry(locking.lock_path(root))
    _record(root, key, _current_survivors(root, cfg, feature, scenario), reason, reviewer)


@mutant_app.command("approve-code")
def mutant_approve_code(
    reason: str = typer.Option(..., "--reason", help="Why these cannot change behavior"),
    reviewer: str = typer.Option("", "--reviewer", help="Who judged them"),
) -> None:
    """Record that the current surviving code mutants are equivalent."""
    root, cfg = resolve_config()
    load_registry(locking.lock_path(root))  # refused before the mutmut run, not after it
    _record(root, SUBJECT, _current_code_survivors(root, cfg), reason, reviewer)


@mutant_app.command("prune")
def mutant_prune(
    feature: Path = typer.Argument(..., help="The feature file to prune approvals for"),
) -> None:
    """Drop approvals for acceptance mutants that no longer survive.

    An assertion got sharper and now kills what a human once judged equivalent.
    The judgment is stale, not wrong — remove it so the ledger stays honest.
    """
    root, cfg = resolve_config()
    key = _feature_key(root, feature)
    approved = load_registry(locking.lock_path(root))  # read once, before the mutation run
    survivors = _current_survivors(root, cfg, feature, "")
    _prune_stale(root, approved, _classify(approved, key, survivors).stale)


@mutant_app.command("prune-code")
def mutant_prune_code() -> None:
    """Drop approvals for code mutants that are no longer produced."""
    root, cfg = resolve_config()
    approved = load_registry(locking.lock_path(root))  # read once, before the mutmut run
    survivors = _current_code_survivors(root, cfg)
    _prune_stale(root, approved, _classify(approved, SUBJECT, survivors).stale)


@mutant_app.command("list")
def mutant_list() -> None:
    """Show every reviewed-equivalent mutant and the reason it was accepted."""
    root, _ = resolve_config()
    approved = load_registry(locking.lock_path(root))
    scoped = registry.in_namespace(approved, mutants_mod.MUTANT_NAMESPACE)
    for key, entry in sorted(scoped.entries.items()):
        reason = entry.reason or "(no reason recorded)"
        typer.echo(f"{registry.bare(key)}\n    {reason}  [{entry.reviewer or 'unknown'}]")
    raise typer.Exit(code=EXIT_OK)


def _read_feature_text(feature: Path) -> str:
    """The bytes of one feature file as text, or a config error naming what stopped it."""
    if not feature.is_file():
        fail(f"no such feature file: {feature}")
    try:
        return feature.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{feature}: not UTF-8 at byte offset {exc.start}")


def _preview_summary(feature: Path, found: list[Mutant]) -> str:
    """The count by kind, because the kinds cost differently to re-review."""
    examples = sum(1 for m in found if m.kind == mutation.KIND_EXAMPLE)
    literals = sum(1 for m in found if m.kind == mutation.KIND_LITERAL)
    return f"{feature}: {len(found)} mutants ({examples} example, {literals} literal)"


@mutant_app.command("preview")
def mutant_preview(
    feature: Path = typer.Argument(..., help="The feature file to enumerate mutants for"),
) -> None:
    """List every mutant one feature file would generate, without running anything.

    Reads the file and nothing else: no project, no approval, no ledger, nothing
    written. One `locator<TAB>signature` line per mutant on stdout, the count by
    kind on stderr; `diff` two listings to see what a spec edit strands.
    Background steps yield no mutants, so a radius read from the listing is a floor.
    """
    text = _read_feature_text(feature)
    try:
        found = mutation.mutants(gherkin.parse(text, str(feature)))
    except gherkin.GherkinError as exc:
        fail(str(exc))
    for mutant in found:
        typer.echo(f"{mutant.locator}\t{mutant.signature}")
    typer.echo(_preview_summary(feature, found), err=True)
    raise typer.Exit(code=EXIT_OK)


def _report_migration(moved: list[tuple[str, str]], unpaired: list[str]) -> NoReturn:
    for old_key, new_key in sorted(moved):
        typer.echo(f"moved  {old_key} -> {new_key}")
    for key in unpaired:
        typer.echo(f"unpaired  {key}")
    typer.echo(
        f"migrated to schema version {registry.SCHEMA_VERSION}: "
        f"{len(moved)} key(s) moved, {len(unpaired)} unpaired"
    )
    raise typer.Exit(code=EXIT_OK)


@mutant_app.command("migrate")
def mutant_migrate() -> None:
    """Rewrite a schema-version-1 ledger to the current version, keeping every judgment.

    A human's command, once per project: the ledger is a protected path. Each
    literal approval moves to the key the engine gives it today, paired by its
    old key and its digest; an approval that pairs to nothing stays under its
    old key, is named here, reads MISSING at the next check, and `mutant prune`
    removes it. No payload changes. A current ledger is left as it is.
    """
    root, _ = resolve_config()
    path = locking.lock_path(root)
    if not path.exists():
        typer.echo(f"no {path.name} to migrate")
        raise typer.Exit(code=EXIT_OK)
    try:
        loaded = registry.load_for_migration(path)
    except registry.RegistryError as exc:
        fail(str(exc))
    if loaded.version == registry.SCHEMA_VERSION:
        typer.echo(f"{path.name} is already at schema version {registry.SCHEMA_VERSION}")
        raise typer.Exit(code=EXIT_OK)
    updated, moved, unpaired = mutants_mod.migrate(root, loaded.registry)
    registry.save(updated, path)
    _report_migration(moved, unpaired)
