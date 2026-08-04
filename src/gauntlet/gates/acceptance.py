"""Acceptance gate: does the code do what the specification says?

Three checks, in order. Every spec must be human-approved and unchanged. The
bound scenarios must pass. And every mutant of a specification value must FAIL —
a surviving mutant means the scenario passes regardless of the values it claims
to test, which makes it decorative.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import config as config_mod
from gauntlet import locking, registry, specs
from gauntlet import mutants as mutants_mod
from gauntlet.acceptance import gherkin, mutation
from gauntlet.acceptance.mutation import Mutant
from gauntlet.adapters import python as python_adapter
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "acceptance"

THRESHOLD = "approved, passing, and mutation-proof"
BACKUP_DIR = Path(".gauntlet") / "mutation-backup"
MAX_LISTED = 6


@dataclass(frozen=True)
class _MutationOutcome:
    diagnostics: list[Diagnostic]
    equivalent: int
    stale: list[str]


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
    return _survivors(
        ctx.project_root, steps, path, chosen, ctx.python, int(config.get("timeout", 600))
    )


def _classify_feature(
    ctx: GateContext, config: dict[str, Any], path: Path, steps: Path, approved: registry.Registry
) -> tuple[list[Diagnostic], int, list[str]]:
    key = specs.key_for(ctx.project_root, path)
    verdict = mutants_mod.classify(approved, key, survivors_for(ctx, config, path, steps))
    return _by_scenario(key, verdict.failing), len(verdict.equivalent), verdict.stale


def _mutation_outcome(
    ctx: GateContext,
    config: dict[str, Any],
    features: list[Path],
    steps: Path,
    approved: registry.Registry,
) -> _MutationOutcome:
    diagnostics: list[Diagnostic] = []
    equivalent = 0
    stale: list[str] = []
    for path in features:
        found, reviewed, gone = _classify_feature(ctx, config, path, steps, approved)
        diagnostics.extend(found)
        equivalent += reviewed
        stale.extend(gone)
    return _MutationOutcome(diagnostics, equivalent, stale)


def _approval_diagnostics(findings: list[registry.Finding]) -> list[Diagnostic]:
    return [
        Diagnostic(
            file=registry.bare(f.key),
            symbol=f.status.value,
            message=registry.describe(f, noun="spec"),
        )
        for f in findings
    ]


def _backup(root: Path, path: Path, text: str) -> None:
    """Keep a copy on disk so a crash mid-mutation is recoverable by hand."""
    destination = root / BACKUP_DIR / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _survivors(
    root: Path, steps: Path, path: Path, mutants: list[mutation.Mutant], python: str, timeout: int
) -> list[mutation.Mutant]:
    """Apply each mutant in place and demand the suite fails. Always restores."""
    original = path.read_text(encoding="utf-8")
    _backup(root, path, original)
    survived: list[mutation.Mutant] = []
    try:
        for mutant in mutants:
            path.write_text(mutation.apply(original, mutant), encoding="utf-8")
            if python_adapter.run_acceptance(root, steps, python, timeout).passed:
                survived.append(mutant)
    finally:
        path.write_text(original, encoding="utf-8")
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
        False, f"{len(findings)} unapproved or modified spec(s)", _approval_diagnostics(findings)
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


def _values(items: list[Mutant]) -> str:
    listed = ", ".join(f"line {m.line}: {m.original}->{m.mutated}" for m in items[:MAX_LISTED])
    extra = len(items) - MAX_LISTED
    return listed + (f" (+{extra} more)" if extra > 0 else "")


def _scenario_diagnostic(path: str, scenario: str, items: list[mutation.Mutant]) -> Diagnostic:
    """One diagnostic per scenario, not per value: thirteen identical sentences
    burn the diagnostic budget and the hook's character cap for no added signal."""
    return Diagnostic(
        file=path,
        symbol=scenario,
        line=min(m.line for m in items),
        value=len(items),
        message=(
            f"{len(items)} surviving mutant(s) in {scenario!r}: {_values(items)}. "
            f"The scenario still passes with these values changed, so it is not "
            f"checking them. Assert on them, or — if the specification maps both "
            f"values to the same outcome — have a human review them with "
            f"`gauntlet mutant approve`."
        ),
    )


def _by_scenario(path: str, items: list[mutation.Mutant]) -> list[Diagnostic]:
    grouped: dict[str, list[mutation.Mutant]] = {}
    for mutant in items:
        grouped.setdefault(mutant.scenario, []).append(mutant)
    return [_scenario_diagnostic(path, scenario, ms) for scenario, ms in grouped.items()]


def _stale_diagnostic(stale: list[str]) -> Diagnostic:
    return Diagnostic(
        file=config_mod.LOCK_FILENAME,
        message=(
            f"{len(stale)} approved equivalent mutant(s) no longer survive — the "
            f"assertions got sharper, so these judgments are stale. Remove them with "
            f"`gauntlet mutant prune`: {', '.join(stale[:3])}" + (" ..." if len(stale) > 3 else "")
        ),
    )


def _survivor_count(diagnostics: list[Diagnostic]) -> int:
    return sum(int(d.value or 0) for d in diagnostics)


def _summary(features: list[Path], outcome: _MutationOutcome) -> str:
    parts = [f"{len(features)} spec(s)"]
    if outcome.diagnostics:
        parts.append(f"{_survivor_count(outcome.diagnostics)} surviving mutant(s)")
    if outcome.equivalent:
        parts.append(f"{outcome.equivalent} reviewed-equivalent")
    if outcome.stale:
        parts.append(f"{len(outcome.stale)} stale approval(s)")
    return ", ".join(parts)


def _mutation_result(features: list[Path], outcome: _MutationOutcome) -> GateResult:
    diagnostics = list(outcome.diagnostics)
    if outcome.stale:
        # Stale approvals are housekeeping, not a defect: report, do not fail.
        diagnostics.append(_stale_diagnostic(outcome.stale))
    return _result(not outcome.diagnostics, _summary(features, outcome), diagnostics)


def _stages(
    ctx: GateContext, config: dict[str, Any], features: list[Path], steps: Path, timeout: int
) -> GateResult:
    approved = registry.load(locking.lock_path(ctx.project_root))
    failure = _approval_stage(ctx, config, features, approved) or _baseline_stage(
        ctx, features, steps, timeout
    )
    if failure is not None:
        return failure
    if not config.get("mutate_examples", True):
        return _result(True, f"{len(features)} spec(s) passing")
    return _mutation_result(features, _mutation_outcome(ctx, config, features, steps, approved))


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    features = specs.discover(ctx.project_root, str(config.get("features", "features/")))
    if not features:
        return _result(True, "no feature files", vacuous=True)
    steps = ctx.project_root / str(config.get("steps", "tests/steps"))
    return _stages(ctx, config, features, steps, int(config.get("timeout", 600)))
