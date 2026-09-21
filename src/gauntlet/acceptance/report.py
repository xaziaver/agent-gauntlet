"""What the acceptance gate says: the diagnostics and the summary line.

The gate decides which state a run is in; this module puts that state into
words. Nothing here runs a scenario, reads the ledger or touches the tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gauntlet import config as config_mod
from gauntlet import registry
from gauntlet.acceptance import mutation
from gauntlet.acceptance.mutation import Mutant
from gauntlet.gates.base import Diagnostic

MAX_LISTED = 6


@dataclass(frozen=True)
class MutationOutcome:
    diagnostics: list[Diagnostic]
    equivalent: int
    stale: list[str]
    not_measured: int = 0  # specs whose mutants would have measured nothing


def merged(outcomes: list[MutationOutcome]) -> MutationOutcome:
    """One feature's outcome at a time, summed for the summary line."""
    total = MutationOutcome([], 0, [])
    for outcome in outcomes:
        total = MutationOutcome(
            total.diagnostics + outcome.diagnostics,
            total.equivalent + outcome.equivalent,
            total.stale + outcome.stale,
            total.not_measured + outcome.not_measured,
        )
    return total


def unbound(key: str, steps: Path) -> str:
    """Why a spec no module binds was not measured: one line, so a CLI can print it as is."""
    return (
        f"no step module under {steps} binds {key}: no `scenarios(...)` names it, and the "
        f"scenarios pass with the file emptied, so its mutants would all survive without "
        f"measuring anything. Add the `scenarios(...)` binding; do not approve its mutants."
    )


def not_measured_diagnostic(key: str, reason: str) -> Diagnostic:
    """No `value`: a spec that was not measured contributes no survivor count."""
    return Diagnostic(file=key, symbol="not measured", message=reason)


def approval_diagnostics(findings: list[registry.Finding]) -> list[Diagnostic]:
    return [
        Diagnostic(
            file=registry.bare(f.key),
            symbol=f.status.value,
            message=registry.describe(f, noun="spec"),
        )
        for f in findings
    ]


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


def by_scenario(path: str, items: list[mutation.Mutant]) -> list[Diagnostic]:
    grouped: dict[str, list[mutation.Mutant]] = {}
    for mutant in items:
        grouped.setdefault(mutant.scenario, []).append(mutant)
    return [_scenario_diagnostic(path, scenario, ms) for scenario, ms in grouped.items()]


def stale_diagnostic(stale: list[str]) -> Diagnostic:
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


def summary(features: list[Path], outcome: MutationOutcome) -> str:
    parts = [f"{len(features)} spec(s)"]
    survivors = _survivor_count(outcome.diagnostics)
    if survivors:
        parts.append(f"{survivors} surviving mutant(s)")
    if outcome.not_measured:
        parts.append(f"{outcome.not_measured} spec(s) not measured")
    if outcome.equivalent:
        parts.append(f"{outcome.equivalent} reviewed-equivalent")
    if outcome.stale:
        parts.append(f"{len(outcome.stale)} stale approval(s)")
    return ", ".join(parts)
