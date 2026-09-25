from __future__ import annotations

from pathlib import Path

from gauntlet import locking, mutants, registry
from gauntlet.acceptance.mutation import KIND_EXAMPLE, Mutant

FEATURE_KEY = "features/triage.feature"


def _mutant(original: str = "75000", mutated: str = "75001", context: str = "amount|75000|10|high"):
    return Mutant(
        scenario="Tiering",
        line=15,
        column=8,
        original=original,
        mutated=mutated,
        kind=KIND_EXAMPLE,
        context=context,
    )


def test_a_new_survivor_is_unreviewed_and_fails(tmp_path: Path) -> None:
    result = mutants.classify(registry.Registry(), FEATURE_KEY, [_mutant()])
    assert [m.original for m in result.unreviewed] == ["75000"]
    assert result.passed is False


def test_an_approved_survivor_is_equivalent_and_passes(tmp_path: Path) -> None:
    mutant = _mutant()
    approved = mutants.approve(tmp_path, FEATURE_KEY, [mutant], reason="same tier")
    result = mutants.classify(approved, FEATURE_KEY, [mutant])
    assert result.equivalent == [mutant]
    assert result.passed is True


def test_the_reason_and_reviewer_are_recorded(tmp_path: Path) -> None:
    approved = mutants.approve(
        tmp_path, FEATURE_KEY, [_mutant()], reason="both map to high", reviewer="xaziaver"
    )
    entry = next(iter(approved.entries.values()))
    assert entry.reason == "both map to high"
    assert entry.reviewer == "xaziaver"


def test_a_different_mutation_at_the_same_spot_needs_re_review(tmp_path: Path) -> None:
    approved = mutants.approve(tmp_path, FEATURE_KEY, [_mutant()], reason="x")
    result = mutants.classify(approved, FEATURE_KEY, [_mutant(mutated="99999")])
    assert len(result.changed) == 1
    assert result.passed is False


def test_an_approved_mutant_that_now_dies_is_reported_stale(tmp_path: Path) -> None:
    """Sharpen an assertion and the ledger flags its own entry for pruning."""
    approved = mutants.approve(tmp_path, FEATURE_KEY, [_mutant()], reason="x")
    result = mutants.classify(approved, FEATURE_KEY, [])
    assert len(result.stale) == 1
    assert result.passed is True


def test_classify_pairs_a_missing_key_to_the_unreviewed_survivor_carrying_its_digest(
    tmp_path: Path,
) -> None:
    """A scenario rename moves the locator; the same mutation survives under a new key
    whose text shares nothing with the old one. The pairing is by digest alone."""
    approved = mutants.approve(tmp_path, FEATURE_KEY, [_mutant()], reason="x")
    moved = Mutant("Renamed", 15, 8, "75000", "75001", KIND_EXAMPLE, "amount|75000|10|high")
    result = mutants.classify(approved, FEATURE_KEY, [moved])
    old_key = mutants.key_for(FEATURE_KEY, _mutant())
    assert result.stale == [old_key]
    assert result.relocated == {old_key: [moved]}
    assert result.unreviewed == [moved]


def test_classify_lists_every_survivor_carrying_a_missing_key_s_digest(tmp_path: Path) -> None:
    """Two survivors with the approved mutation: the human chooses which one moved."""
    approved = mutants.approve(tmp_path, FEATURE_KEY, [_mutant()], reason="x")
    twins = [_mutant(context="amount|75000|10|HIGH"), _mutant(context="amount|75000|11|high")]
    result = mutants.classify(approved, FEATURE_KEY, twins)
    assert result.relocated == {mutants.key_for(FEATURE_KEY, _mutant()): twins}


def test_classify_leaves_a_missing_key_unpaired_when_no_survivor_carries_its_digest(
    tmp_path: Path,
) -> None:
    """A survivor whose locator text is nearly the old key's but whose mutation differs
    is not the moved judgment: the key is superseded, and stays in `stale`."""
    approved = mutants.approve(tmp_path, FEATURE_KEY, [_mutant()], reason="x")
    near = _mutant(mutated="99999", context="amount|75000|10|high ")
    result = mutants.classify(approved, FEATURE_KEY, [near])
    assert result.stale == [mutants.key_for(FEATURE_KEY, _mutant())]
    assert result.relocated == {}
    assert result.unreviewed == [near]


def test_approving_one_mutant_leaves_other_namespaces_alone(tmp_path: Path) -> None:
    seeded = registry.approve(registry.Registry(), "spec:features/triage.feature", b"x")
    registry.save(seeded, locking.lock_path(tmp_path))
    approved = mutants.approve(tmp_path, FEATURE_KEY, [_mutant()], reason="x")
    assert "spec:features/triage.feature" in approved.entries


def test_one_subject_never_reports_another_subject_s_approvals_as_stale(tmp_path: Path) -> None:
    """prune-code would otherwise delete every acceptance approval."""
    approved = mutants.approve(tmp_path, "features/a.feature", [_mutant()], reason="x")
    result = mutants.classify(approved, "code", [])
    assert result.stale == []
