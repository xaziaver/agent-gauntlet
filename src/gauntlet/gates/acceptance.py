"""Acceptance gate: does the code do what the specification says?

Three checks, in order. Every spec must be human-approved and unchanged. The
bound scenarios must pass. And every mutant of a specification value must FAIL —
a surviving mutant means the scenario passes regardless of the values it claims
to test, which makes it decorative.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gauntlet import locking, registry, specs
from gauntlet.acceptance import gherkin, mutation
from gauntlet.adapters import python as python_adapter
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "acceptance"

THRESHOLD = "approved, passing, and mutation-proof"
BACKUP_DIR = Path(".gauntlet") / "mutation-backup"


def _approval_diagnostics(findings: list[registry.Finding]) -> list[Diagnostic]:
    return [
        Diagnostic(
            file=registry.bare(f.key),
            symbol=f.status.value,
            message=registry.describe(f, noun="spec"),
        )
        for f in findings
    ]


def _survivor_diagnostic(path: str, mutant: mutation.Mutant) -> Diagnostic:
    return Diagnostic(
        file=path,
        symbol=mutant.scenario,
        line=mutant.line,
        message=(
            f"Surviving mutant: {mutant.original} -> {mutant.mutated}. The scenario "
            f"{mutant.scenario!r} still passes with this value changed, so it is not "
            f"actually checking it. Bind the step to the real system and assert on "
            f"this value."
        ),
    )


def _backup(root: Path, path: Path, text: str) -> None:
    """Keep a copy on disk so a crash mid-mutation is recoverable by hand."""
    destination = root / BACKUP_DIR / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _survivors(
    root: Path, steps: Path, path: Path, mutants: list[mutation.Mutant], timeout: int
) -> list[mutation.Mutant]:
    """Apply each mutant in place and demand the suite fails. Always restores."""
    original = path.read_text(encoding="utf-8")
    _backup(root, path, original)
    survived: list[mutation.Mutant] = []
    try:
        for mutant in mutants:
            path.write_text(mutation.apply(original, mutant), encoding="utf-8")
            if python_adapter.run_acceptance(root, steps, timeout).passed:
                survived.append(mutant)
    finally:
        path.write_text(original, encoding="utf-8")
    return survived


def _mutation_diagnostics(
    ctx: GateContext, config: dict[str, Any], features: list[Path], steps: Path
) -> list[Diagnostic]:
    limit = int(config.get("mutation_sample", 0))
    timeout = int(config.get("timeout", 600))
    diagnostics: list[Diagnostic] = []
    for path in features:
        text = path.read_text(encoding="utf-8")
        candidates = mutation.mutants(gherkin.parse(text, str(path)))
        chosen = mutation.sample(candidates, limit)
        key = specs.key_for(ctx.project_root, path)
        diagnostics.extend(
            _survivor_diagnostic(key, m)
            for m in _survivors(ctx.project_root, steps, path, chosen, timeout)
        )
    return diagnostics


def _result(passed: bool, actual: str, diagnostics: list[Diagnostic] | None = None) -> GateResult:
    return GateResult(
        gate=name,
        passed=passed,
        threshold=THRESHOLD,
        actual=actual,
        diagnostics=diagnostics or [],
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
    baseline = python_adapter.run_acceptance(ctx.project_root, steps, timeout)
    if baseline.passed:
        return None
    return GateResult(
        gate=name,
        passed=False,
        threshold=THRESHOLD,
        actual=f"{len(features)} spec(s), scenarios failing",
        diagnostics=[Diagnostic(file=str(steps), message=baseline.output[:800])],
    )


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
    survivors = _mutation_diagnostics(ctx, config, features, steps)
    return _result(
        not survivors, f"{len(features)} spec(s), {len(survivors)} surviving mutant(s)", survivors
    )


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    features = specs.discover(ctx.project_root, str(config.get("features", "features/")))
    if not features:
        return _result(True, "no feature files")
    steps = ctx.project_root / str(config.get("steps", "tests/steps"))
    return _stages(ctx, config, features, steps, int(config.get("timeout", 600)))
