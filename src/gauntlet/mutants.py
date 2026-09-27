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

The ledger helpers are generic over the kind of mutant, acceptance or code,
while the migration is acceptance-specific: it re-enumerates literal mutants
from the spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from gauntlet import locking, registry
from gauntlet.acceptance import gherkin, mutation

MUTANT_NAMESPACE = "mutant"
SUBJECT_SEPARATOR = "#"
# A schema-version-1 literal key ended at the step text; version 2 appends the
# literal's offset within it, so migration pairs on everything before that.
OFFSET_SEPARATOR = "|@"


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
    # A stale key paired to the unreviewed survivors carrying its digest: the judgment
    # moved with a spec edit rather than lapsed. A stale key absent here is superseded.
    relocated: dict[str, list[M]] = field(default_factory=dict)

    @property
    def failing(self) -> list[M]:
        return [*self.unreviewed, *self.changed]

    @property
    def passed(self) -> bool:
        return not self.failing


def key_for(subject_key: str, mutant: MutantLike) -> str:
    """Ledger key: the subject it lives in (feature file or module), plus the locator."""
    return f"{subject_key}{SUBJECT_SEPARATOR}{mutant.locator}"


def _split_key(key: str) -> tuple[str, str]:
    """`mutant:<subject>#<locator>` -> (subject, locator), at the first `#`."""
    subject, _, locator = registry.bare(key).partition(SUBJECT_SEPARATOR)
    return subject, locator


def subject_of(key: str) -> str:
    """The subject a ledger key lives in: the feature file for an acceptance mutant."""
    return _split_key(key)[0]


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


def _relocated(findings: list[registry.Finding], unreviewed: list[M]) -> dict[str, list[M]]:
    """Each MISSING key paired, by digest alone, to the unreviewed survivors whose
    mutation it approved: the locator moved under an edit and the judgment stands.
    A key no survivor's digest matches is superseded — the mutant now dies — and
    is left out, so its judgment is not offered for re-approval."""
    by_digest: dict[str, list[M]] = {}
    for mutant in unreviewed:
        by_digest.setdefault(registry.digest(mutant.signature.encode("utf-8")), []).append(mutant)
    return {
        registry.bare(f.key): by_digest[f.expected]
        for f in findings
        if f.status is registry.Status.MISSING and f.expected in by_digest
    }


def _subject_scope(approved: registry.Registry, subject_key: str) -> registry.Registry:
    """Only approvals belonging to this subject.

    The mutant namespace holds acceptance and code approvals together. Without
    scoping, a code-mutant run reports every acceptance approval as stale — and
    `prune-code` would delete them.
    """
    prefix = f"{subject_key}{SUBJECT_SEPARATOR}"
    scoped = registry.in_namespace(approved, MUTANT_NAMESPACE)
    return registry.Registry(
        entries={k: v for k, v in scoped.entries.items() if registry.bare(k).startswith(prefix)}
    )


def classify(
    approved: registry.Registry, subject_key: str, survivors: list[M]
) -> Classification[M]:
    """Split survivors against the ledger.
    MISSING means an approved equivalent no longer survives at its key, for one of
    two causes: the assertion got sharper and the mutant now dies (superseded), or
    a spec edit moved the locator while the same mutation survives at a new one
    (relocated — paired by digest in `relocated`). Either way the judgment is stale
    at that key and the entry should be pruned. That is the self-invalidation
    requirement, and it comes free from verify_all.
    """
    by_key = {key_for(subject_key, m): m for m in survivors}
    findings = registry.verify_namespace(
        _subject_scope(approved, subject_key), MUTANT_NAMESPACE, subjects(subject_key, survivors)
    )
    result: Classification[M] = Classification()
    for finding in findings:
        _place(result, finding, by_key.get(registry.bare(finding.key)))
    result.relocated.update(_relocated(findings, result.unreviewed))
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


def _is_literal_key(key: str) -> bool:
    """An entry whose locator names the literal kind.

    Only a `mutant:` key carries a `#`-separated locator; a `spec:` or `config:`
    key is a path, so its locator is empty and it is never a literal.
    """
    return f"|{mutation.KIND_LITERAL}|" in _split_key(key)[1]


def _spec_mutants(root: Path, subject: str) -> list[mutation.Mutant] | None:
    """Every mutant the engine enumerates for one spec, or None where it cannot read it."""
    try:
        text = (root / subject).read_text(encoding="utf-8")
        return mutation.mutants(gherkin.parse(text, subject))
    except (OSError, UnicodeDecodeError, gherkin.GherkinError):
        return None


def _spec_mutants_once(
    cache: dict[str, list[mutation.Mutant] | None], root: Path, subject: str
) -> list[mutation.Mutant]:
    """One enumeration per spec, however many approvals point at it."""
    if subject not in cache:
        cache[subject] = _spec_mutants(root, subject)
    return cache[subject] or []


def _without_offset(locator: str) -> str:
    """The version-1 form of a literal locator: everything before the trailing `|@<offset>`."""
    head, _, _ = locator.rpartition(OFFSET_SEPARATOR)
    return head


def _paired_key(
    candidates: list[mutation.Mutant], subject: str, locator: str, approved_digest: str
) -> str | None:
    """The current key of one version-1 literal approval, or None where it pairs to nothing.

    The old locator and the approval's digest are matched against one spec's
    mutants as the engine enumerates them today. Two matches — one line
    carrying the same literal twice with the same substitution — are as
    unpairable as none: the entry is left for a human.
    """
    matched = [
        m.locator
        for m in candidates
        if m.kind == mutation.KIND_LITERAL
        and _without_offset(m.locator) == locator
        and registry.digest(m.signature.encode("utf-8")) == approved_digest
    ]
    if len(matched) != 1:
        return None
    return registry.namespaced(MUTANT_NAMESPACE, subject + SUBJECT_SEPARATOR + matched[0])


def migrate(
    root: Path, approved: registry.Registry
) -> tuple[registry.Registry, list[tuple[str, str]], list[str]]:
    """Re-key every literal approval to the current locator form, judgments untouched.

    Returns the re-keyed registry, the `(old_key, new_key)` pairs it moved, and
    the keys it could not pair, which stay under their old key: each reads
    MISSING at the next check and `mutant prune` removes it. Every entry that is
    not a literal mutant is carried unchanged, and no payload is touched.
    """
    entries = dict(approved.entries)
    moved: list[tuple[str, str]] = []
    unpaired: list[str] = []
    cache: dict[str, list[mutation.Mutant] | None] = {}
    for key in sorted(k for k in approved.entries if _is_literal_key(k)):
        subject, locator = _split_key(key)
        candidates = _spec_mutants_once(cache, root, subject)
        new_key = _paired_key(candidates, subject, locator, entries[key].digest)
        if new_key is None:
            unpaired.append(key)
            continue
        entries[new_key] = entries.pop(key)
        moved.append((key, new_key))
    return registry.Registry(entries=entries), moved, unpaired
