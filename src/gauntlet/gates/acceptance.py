"""Acceptance gate: does the code do what the specification says?

Three checks, in order. Every spec must be human-approved and unchanged. The
bound scenarios must pass. And every mutant of a specification value must FAIL —
a surviving mutant means the scenario passes regardless of the values it claims
to test, which makes it decorative.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from gauntlet import locking, registry, specs
from gauntlet import mutants as mutants_mod
from gauntlet.acceptance import binding, gherkin, mutation, report, strands
from gauntlet.acceptance.mutation import Mutant
from gauntlet.adapters import python as python_adapter
from gauntlet.gates import base
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "acceptance"

THRESHOLD = "approved, passing, and mutation-proof"
SCOPE_RECORD = Path(".gauntlet") / "acceptance-scope.json"
NOT_RUN = "; mutation not run"


def survivors_for(
    ctx: GateContext, config: dict[str, Any], path: Path, steps: Path
) -> list[Mutant]:
    """Mutants of one feature that the bound scenarios fail to kill.

    Public so the `gauntlet mutant` commands share the gate's code path: the CLI
    must never disagree with the gate about what survived.
    """
    text = path.read_text(encoding="utf-8")
    candidates = mutation.mutants(gherkin.parse(text, str(path)))
    chosen = mutation.sample(candidates, int(config.get("mutation_sample", 0)))
    targets = targets_for(config, steps, path)
    return _survivors(
        ctx.project_root, targets, path, chosen, ctx.python, int(config.get("timeout", 600))
    )


def targets_for(config: dict[str, Any], steps: Path, feature: Path) -> list[Path]:
    """The paths one feature's mutants run against.

    The step module(s) that bind the feature, rediscovered from the step files on
    every call; a feature no module binds runs the whole directory — more
    enforcement, not less. `scope = "directory"` restores the whole-directory run
    for every feature, for comparison.
    """
    if config.get("scope", "module") == "directory":
        return [steps]
    return binding.bound_modules(steps, feature) or [steps]


def _classify_feature(
    ctx: GateContext, config: dict[str, Any], path: Path, steps: Path, approved: registry.Registry
) -> tuple[list[Diagnostic], int, list[str]]:
    key = specs.key_for(ctx.project_root, path)
    verdict = mutants_mod.classify(approved, key, survivors_for(ctx, config, path, steps))
    return report.by_scenario(key, verdict.failing), len(verdict.equivalent), verdict.stale


def _mutation_outcome(
    ctx: GateContext,
    config: dict[str, Any],
    features: list[Path],
    steps: Path,
    approved: registry.Registry,
) -> report.MutationOutcome:
    diagnostics: list[Diagnostic] = []
    equivalent = 0
    stale: list[str] = []
    for path in features:
        found, reviewed, gone = _classify_feature(ctx, config, path, steps, approved)
        diagnostics.extend(found)
        equivalent += reviewed
        stale.extend(gone)
    _record_scope(ctx, config, features, steps)
    return report.MutationOutcome(diagnostics, equivalent, stale)


def _record_scope(
    ctx: GateContext, config: dict[str, Any], features: list[Path], steps: Path
) -> None:
    """Write which paths each feature's mutants ran against. Rewritten every mutation
    stage and read by nothing: a gate has no event sink, so the record is a file."""
    root = ctx.project_root
    record = {
        "scope": str(config.get("scope", "module")),
        "features": {
            specs.key_for(root, path): [
                target.relative_to(root).as_posix() for target in targets_for(config, steps, path)
            ]
            for path in features
        },
    }
    destination = root / SCOPE_RECORD
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _survivors(
    root: Path,
    targets: list[Path],
    path: Path,
    mutants: list[mutation.Mutant],
    python: str,
    timeout: int,
) -> list[mutation.Mutant]:
    """Apply each mutant in place and demand the targets fail. Always restores."""
    original = path.read_text(encoding="utf-8")
    strands.backup(root, path, original)
    survived: list[mutation.Mutant] = []
    with base.signals_raise():
        try:
            for mutant in mutants:
                base.write_text_atomic(path, mutation.apply(original, mutant))
                if python_adapter.run_acceptance(root, targets, python, timeout).passed:
                    survived.append(mutant)
        finally:
            base.write_text_atomic(path, original)
            strands.discard(root, path)
    return survived


def _result(
    passed: bool, actual: str, diagnostics: list[Diagnostic] | None = None, vacuous: bool = False
) -> GateResult:
    return GateResult(
        gate=name,
        passed=passed,
        threshold=THRESHOLD,
        actual=actual,
        diagnostics=diagnostics or [],
        vacuous=vacuous,
    )


def _approval_stage(
    ctx: GateContext, config: dict[str, Any], features: list[Path], approved: registry.Registry
) -> GateResult | None:
    if not config.get("require_approved", True):
        return None
    findings = specs.verify(ctx.project_root, features, approved)
    if not findings:
        return None
    return _result(
        False,
        f"{len(findings)} unapproved or modified spec(s)",
        report.approval_diagnostics(findings),
    )


def _baseline_stage(
    ctx: GateContext, features: list[Path], steps: Path, timeout: int
) -> GateResult | None:
    baseline = python_adapter.run_acceptance(ctx.project_root, steps, ctx.python, timeout)
    if baseline.passed:
        return None
    return GateResult(
        gate=name,
        passed=False,
        threshold=THRESHOLD,
        actual=f"{len(features)} spec(s), scenarios failing",
        diagnostics=[Diagnostic(file=str(steps), message=baseline.output[:800])],
    )


def _mutation_result(features: list[Path], outcome: report.MutationOutcome) -> GateResult:
    diagnostics = list(outcome.diagnostics)
    if outcome.stale:
        # Stale approvals are housekeeping, not a defect: report, do not fail.
        diagnostics.append(report.stale_diagnostic(outcome.stale))
    return _result(not outcome.diagnostics, report.summary(features, outcome), diagnostics)


def _stages(
    ctx: GateContext, config: dict[str, Any], features: list[Path], steps: Path, timeout: int
) -> GateResult:
    approved = registry.load(locking.lock_path(ctx.project_root))
    failure = _approval_stage(ctx, config, features, approved) or _baseline_stage(
        ctx, features, steps, timeout
    )
    if failure is not None:
        # Report, do not run: the stage that would have run says so in the summary.
        return dataclasses.replace(failure, actual=f"{failure.actual}{NOT_RUN}")
    if not config.get("mutate_examples", True):
        return _result(True, f"{len(features)} spec(s) passing")
    return _mutation_result(features, _mutation_outcome(ctx, config, features, steps, approved))


def _with_restored(result: GateResult, restored: int) -> GateResult:
    """Say so when the run began by undoing a strand; a clean run's result is untouched."""
    if restored == 0:
        return result
    actual = f"{restored} stranded spec(s) restored; {result.actual}"
    return dataclasses.replace(result, actual=actual)


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    features_dir = str(config.get("features", "features/"))
    restored = strands.restore_all(ctx.project_root, ctx.project_root / features_dir)
    features = specs.discover(ctx.project_root, features_dir)
    if not features:
        return _result(True, "no feature files", vacuous=True)
    steps = ctx.project_root / str(config.get("steps", "tests/steps"))
    result = _stages(ctx, config, features, steps, int(config.get("timeout", 600)))
    return _with_restored(result, restored)
