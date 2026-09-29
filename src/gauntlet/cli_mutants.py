"""The `gauntlet mutant` sub-app: classify surviving acceptance mutants."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NoReturn, TypeVar

import typer

from gauntlet import config as config_mod
from gauntlet import events, locking, mutant_scope, registry, runner, specs
from gauntlet import mutants as mutants_mod
from gauntlet.acceptance import gherkin, mutation
from gauntlet.acceptance.mutation import Mutant
from gauntlet.adapters.python import CodeMutant
from gauntlet.cli_support import EXIT_OK, fail, load_registry, resolve_config
from gauntlet.gates import acceptance, base
from gauntlet.gates.mutation import SUBJECT, MutmutError, survivors_for

mutant_app = typer.Typer(no_args_is_help=True, help="Review surviving mutants.")

NOTHING_UNREVIEWED = "no unreviewed survivors to approve"
REWRITE_HELP = "Also re-record approved survivors in scope, with this reason and today's date"

M = TypeVar("M", bound=mutants_mod.MutantLike)


def _classify(
    approved: registry.Registry, subject_key: str, survivors: list[M]
) -> mutants_mod.Classification[M]:
    return mutants_mod.classify(approved, subject_key, survivors)


def _record(
    root: Path,
    subject_key: str,
    chosen: tuple[list[M], list[M]],
    rewrite: bool,
    reason: str,
    reviewer: str,
) -> NoReturn:
    """The approval ceremony, shared by acceptance and code mutants: write what
    `mutants.to_record` chose, log it, and say which were re-recorded."""
    written, rewritten = chosen
    if not written:
        typer.echo("no surviving mutants to record" if rewrite else NOTHING_UNREVIEWED)
        raise typer.Exit(code=EXIT_OK)
    updated = mutants_mod.approve(root, subject_key, written, reason=reason, reviewer=reviewer)
    registry.save(updated, locking.lock_path(root))
    events.Log(root).emit(
        events.APPROVAL_GRANTED,
        subject=subject_key,
        namespace=mutants_mod.MUTANT_NAMESPACE,
        count=len(written),
    )
    for mutant in written:
        typer.echo(f"{'rewritten' if mutant in rewritten else 'approved'}  {mutant.description}")
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


def _first_line(output: str) -> str:
    return next((line for line in output.splitlines() if line.strip()), "")


def _require_green_baseline(ctx: base.GateContext, config: dict[str, Any], steps: Path) -> None:
    """The baseline first, as the gate runs it: on a red suite every mutant "dies" and
    every approval would read stale, so the command refuses before it classifies."""
    suite = acceptance.baseline(ctx, steps, int(config.get("timeout", 600)))
    if not suite.passed:
        fail(f"baseline suite failing; refusing to classify survivors: {_first_line(suite.output)}")


def _current_survivors(
    root: Path, cfg: config_mod.Config, feature: Path, scenario: str, locators: list[str]
) -> list[Mutant]:
    """Re-run the mutation loop for one feature, through the gate's own helpers, and
    keep the survivors the scope names."""
    config = _acceptance_config(cfg)
    ctx = runner.build_context(root, cfg, cfg.enabled_gates, changed=False)
    steps = root / str(config.get("steps", "tests/steps"))
    _require_green_baseline(ctx, config, steps)
    try:
        survivors = acceptance.survivors_for(ctx, config, feature, steps)
        return mutant_scope.in_scope(survivors, scenario, locators)
    except base.Interrupted as exc:
        exc.die()  # the gate's finally has already restored the spec
    except acceptance.NotMeasuredError as exc:
        fail(str(exc))  # the gate's sentence, and nothing written
    except mutant_scope.ScopeError as exc:
        fail(f"no current survivor of {feature} at locator {str(exc)!r}; nothing written")


def _unnarrowed(scenario: str, locator: list[str], all_scenarios: bool) -> bool:
    """Refuse --all-scenarios beside a narrower filter; True when no flag names the scope."""
    if all_scenarios and (scenario or locator):
        fail("--all-scenarios cannot narrow: drop it, or drop --scenario and --locator")
    return not (scenario or locator or all_scenarios)


def _refuse_a_sweep(written: list[Mutant]) -> None:
    """More than one scenario's survivors under one reason is the sweep to refuse."""
    if scenarios := mutant_scope.swept(written):
        named = ", ".join(repr(s) for s in scenarios)
        fail(
            f"{len(scenarios)} scenarios hold survivors to approve ({named}): name one "
            f"with --scenario, one mutant with --locator, or pass --all-scenarios"
        )


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
    locator: list[str] = typer.Option([], "--locator", help="Only the survivor at this locator"),
    all_scenarios: bool = typer.Option(False, "--all-scenarios", help="Every scenario at once"),
    rewrite: bool = typer.Option(False, "--rewrite", help=REWRITE_HELP),
) -> None:
    """Record that the current acceptance survivors are equivalent mutants.

    This is a judgment about the domain, not a way to silence a gate: an
    equivalent mutant is one the specification cannot distinguish. The reason is
    required because it is what a future reviewer needs. Only unreviewed survivors
    are written, and one scenario at a time unless --all-scenarios says otherwise.
    """
    unnarrowed = _unnarrowed(scenario, locator, all_scenarios)
    root, cfg = resolve_config()
    key = _feature_key(root, feature)
    approved = load_registry(locking.lock_path(root))  # refused before the mutation run
    in_scope = _current_survivors(root, cfg, feature, scenario, locator)
    chosen = mutants_mod.to_record(approved, key, in_scope, rewrite)
    if unnarrowed:
        _refuse_a_sweep(chosen[0])
    _record(root, key, chosen, rewrite, reason, reviewer)


@mutant_app.command("approve-code")
def mutant_approve_code(
    reason: str = typer.Option(..., "--reason", help="Why these cannot change behavior"),
    reviewer: str = typer.Option("", "--reviewer", help="Who judged them"),
    rewrite: bool = typer.Option(False, "--rewrite", help=REWRITE_HELP),
) -> None:
    """Record that the current unreviewed code mutants are equivalent."""
    root, cfg = resolve_config()
    approved = load_registry(locking.lock_path(root))  # refused before the mutmut run
    chosen = mutants_mod.to_record(approved, SUBJECT, _current_code_survivors(root, cfg), rewrite)
    _record(root, SUBJECT, chosen, rewrite, reason, reviewer)


@mutant_app.command("prune")
def mutant_prune(
    feature: Path = typer.Argument(..., help="The feature file to prune approvals for"),
) -> None:
    """Drop approvals for acceptance mutants that no longer survive at their key.

    Two causes, which the gate's diagnostic tells apart: an assertion got sharper
    and now kills what a human once judged equivalent (superseded — do not
    re-approve without review), or a spec edit moved the locator and the same
    mutation survives at a new one (relocated — re-approve it there). Either way
    the entry is stale at its key; remove it so the ledger stays honest.
    """
    root, cfg = resolve_config()
    key = _feature_key(root, feature)
    approved = load_registry(locking.lock_path(root))  # read once, before the mutation run
    survivors = _current_survivors(root, cfg, feature, "", [])
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
