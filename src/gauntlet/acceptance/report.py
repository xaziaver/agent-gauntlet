"""What the acceptance gate says: the diagnostics and the summary line.

The gate decides which state a run is in; this module puts that state into
words. Nothing here runs a scenario, reads the ledger or touches the tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gauntlet import config as config_mod
from gauntlet import mutants as mutants_mod
from gauntlet import registry
from gauntlet.acceptance.mutation import Mutant
from gauntlet.gates.base import Diagnostic

MAX_LISTED = 6


@dataclass(frozen=True)
class MutationOutcome:
    diagnostics: list[Diagnostic]
    equivalent: int
    stale: list[str]
    not_measured: int = 0  # specs whose mutants would have measured nothing
    # The stale keys whose judgment moved, each with the survivors carrying its digest.
    relocated: dict[str, list[Mutant]] = field(default_factory=dict)


def merged(outcomes: list[MutationOutcome]) -> MutationOutcome:
    """One feature's outcome at a time, summed for the summary line."""
    total = MutationOutcome([], 0, [])
    for outcome in outcomes:
        total = MutationOutcome(
            total.diagnostics + outcome.diagnostics,
            total.equivalent + outcome.equivalent,
            total.stale + outcome.stale,
            total.not_measured + outcome.not_measured,
            {**total.relocated, **outcome.relocated},
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
    """A spec is approved by `gauntlet spec approve`, the same command `gauntlet status` names."""
    return [
        Diagnostic(
            file=registry.bare(f.key),
            symbol=f.status.value,
            message=registry.describe(
                f, noun="spec", command=f"gauntlet spec approve {registry.bare(f.key)}"
            ),
        )
        for f in findings
    ]


def _value(m: Mutant, re_aimed: frozenset[Mutant]) -> str:
    """A re-aimed mutant is approved at this locator, but for a substitution that a
    neighbouring edit has since changed under the key: the judgment does not carry."""
    listed = f"line {m.line}: {m.signature}"
    if m in re_aimed:
        listed += (
            f" (approved at this locator for a different substitution; the judgment "
            f"was not about `{m.signature}`)"
        )
    return listed


def _values(items: list[Mutant], re_aimed: frozenset[Mutant]) -> str:
    listed = ", ".join(_value(m, re_aimed) for m in items[:MAX_LISTED])
    extra = len(items) - MAX_LISTED
    return listed + (f" (+{extra} more)" if extra > 0 else "")


def _scenario_diagnostic(
    path: str, scenario: str, items: list[Mutant], re_aimed: frozenset[Mutant]
) -> Diagnostic:
    """One diagnostic per scenario, not per value: thirteen identical sentences
    burn the diagnostic budget and the hook's character cap for no added signal."""
    return Diagnostic(
        file=path,
        symbol=scenario,
        line=min(m.line for m in items),
        value=len(items),
        message=(
            f"{len(items)} surviving mutant(s) in {scenario!r}: {_values(items, re_aimed)}. "
            f"The scenario still passes with these values changed, so it is not "
            f"checking them. Assert on them, or — if the specification maps both "
            f"values to the same outcome — have a human review them with "
            f"`gauntlet mutant approve`."
        ),
    )


def by_scenario(path: str, items: list[Mutant], changed: list[Mutant]) -> list[Diagnostic]:
    """`items` are the failing survivors; those also in `changed` are re-aimed."""
    grouped: dict[str, list[Mutant]] = {}
    for mutant in items:
        grouped.setdefault(mutant.scenario, []).append(mutant)
    re_aimed = frozenset(changed)
    return [_scenario_diagnostic(path, s, ms, re_aimed) for s, ms in grouped.items()]


def _listed(items: list[str]) -> str:
    return ", ".join(items[:3]) + (" ..." if len(items) > 3 else "")


def _prune_lines(keys: list[str]) -> str:
    """One runnable `gauntlet mutant prune <feature>` per feature holding a key."""
    features = sorted({mutants_mod.subject_of(key) for key in keys})
    return ", ".join(f"`gauntlet mutant prune {feature}`" for feature in features)


def _relocated_diagnostic(relocated: dict[str, list[Mutant]]) -> Diagnostic:
    pairs = [
        f"{registry.bare(key).partition(mutants_mod.SUBJECT_SEPARATOR)[2]} -> {m.locator}"
        for key, survivors in relocated.items()
        for m in survivors
    ]
    return Diagnostic(
        file=config_mod.LOCK_FILENAME,
        symbol="relocated",
        message=(
            f"{len(relocated)} approved equivalent mutant(s) moved — a spec edit changed the "
            f"locator and the same mutation still survives at a new one, so the judgment "
            f"still holds: {_listed(pairs)}; prune the old key, then re-approve at the "
            f"new locator: {_prune_lines(list(relocated))}"
        ),
    )


def _superseded_diagnostic(superseded: list[str]) -> Diagnostic:
    return Diagnostic(
        file=config_mod.LOCK_FILENAME,
        symbol="superseded",
        message=(
            f"{len(superseded)} approved equivalent mutant(s) no longer survive at any "
            f"locator — an assertion now kills them, so the judgment is not re-approved "
            f"without review: {_listed(superseded)}; remove them with "
            f"{_prune_lines(superseded)}"
        ),
    )


def stale_diagnostics(stale: list[str], relocated: dict[str, list[Mutant]]) -> list[Diagnostic]:
    """Up to two diagnostics on the lock, one per cause present: relocated keys are
    the stale keys paired to a survivor by digest; every other stale key is superseded."""
    diagnostics: list[Diagnostic] = []
    if relocated:
        diagnostics.append(_relocated_diagnostic(relocated))
    superseded = [key for key in stale if key not in relocated]
    if superseded:
        diagnostics.append(_superseded_diagnostic(superseded))
    return diagnostics


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
