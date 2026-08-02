"""The equivalent-mutant ledger.

A surviving mutant is not automatically a defect. When the specification maps
the original and mutated values to the same outcome — 75000 and 75001 are both
"high" — no assertion can kill it. That is an equivalent mutant: a statement
about the domain, not a weakness in the tests.

Left unmanaged, equivalent mutants pollute the score and train everyone to
ignore survivors. So they are classified once by a human, recorded with a
reason, and thereafter treated as reviewed. The four registry statuses map
exactly onto the four things that can happen to a survivor, so this module is
mostly naming, not machinery.

Generic over the kind of mutant: acceptance mutants perturb specification
values, code mutants perturb the implementation, and both need exactly this
lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from gauntlet import locking, registry

MUTANT_NAMESPACE = "mutant"


class MutantLike(Protocol):
    @property
    def locator(self) -> str:
        """Stable structural identity — never line-based."""

    @property
    def signature(self) -> str:
        """The mutation itself; its hash is what an approval records."""

    @property
    def description(self) -> str:
        """One human-readable line, for approval output."""


M = TypeVar("M", bound=MutantLike)


@dataclass(frozen=True)
class Classification(Generic[M]):
    """Survivors split by what the human has already said about them."""

    unreviewed: list[M] = field(default_factory=list)  # never judged -> fail
    changed: list[M] = field(default_factory=list)  # judgment lapsed -> fail
    equivalent: list[M] = field(default_factory=list)  # judged equivalent -> pass
    stale: list[str] = field(default_factory=list)  # approved, no longer survives

    @property
    def failing(self) -> list[M]:
        return [*self.unreviewed, *self.changed]

    @property
    def passed(self) -> bool:
        return not self.failing


def key_for(subject_key: str, mutant: MutantLike) -> str:
    """Ledger key: the subject it lives in (feature file or module), plus the locator."""
    return f"{subject_key}#{mutant.locator}"


def subjects(subject_key: str, survivors: list[M]) -> dict[str, bytes]:
    return {key_for(subject_key, m): m.signature.encode("utf-8") for m in survivors}


def _bucket_for(result: Classification[M], status: registry.Status) -> list[M] | None:
    """Which list a finding lands in. MISSING is handled separately: it names a
    stale entry, not a mutant we just saw."""
    buckets: dict[registry.Status, list[M]] = {
        registry.Status.UNCHANGED: result.equivalent,
        registry.Status.MODIFIED: result.changed,
        registry.Status.UNAPPROVED: result.unreviewed,
    }
    return buckets.get(status)


def _place(result: Classification[M], finding: registry.Finding, mutant: M | None) -> None:
    if finding.status is registry.Status.MISSING:
        result.stale.append(registry.bare(finding.key))
        return
    bucket = _bucket_for(result, finding.status)
    if bucket is not None and mutant is not None:
        bucket.append(mutant)


def classify(
    approved: registry.Registry, subject_key: str, survivors: list[M]
) -> Classification[M]:
    """Split survivors against the ledger.
    MISSING means an approved equivalent no longer survives — the assertion got
    sharper, so the judgment is stale and the entry should be pruned. That is
    the self-invalidation requirement, and it comes free from verify_all.
    """
    by_key = {key_for(subject_key, m): m for m in survivors}
    findings = registry.verify_namespace(
        approved, MUTANT_NAMESPACE, subjects(subject_key, survivors)
    )
    result: Classification[M] = Classification()
    for finding in findings:
        _place(result, finding, by_key.get(registry.bare(finding.key)))
    return result


def approve(
    root: Path, subject_key: str, survivors: list[M], reason: str, reviewer: str = ""
) -> registry.Registry:
    """Record a human judgment that these survivors cannot change behavior."""
    current = registry.load(locking.lock_path(root))
    for mutant in survivors:
        current = registry.approve(
            current,
            registry.namespaced(MUTANT_NAMESPACE, key_for(subject_key, mutant)),
            mutant.signature.encode("utf-8"),
            reason=reason,
            reviewer=reviewer,
        )
    return current
