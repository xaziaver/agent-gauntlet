from __future__ import annotations

import pytest

from gauntlet.acceptance import gherkin, mutation

FEATURE = """\
Feature: Premium rating

  Scenario: Pro-rata cancellation
    Given an annual premium of 1200
    When the policy is cancelled after 182 days
    Then the earned premium is 596.72

  Scenario Outline: Methods
    Given an annual premium of <premium>
    When cancelled by <method>
    Then the earned premium is <earned>

    Examples:
      | premium | method      | earned | refundable |
      | 1200    | pro_rata    | 596.72 | true       |
      | 1200    | short_rate  | 657.05 | false      |
"""


def _mutants() -> list[mutation.Mutant]:
    return mutation.mutants(gherkin.parse(FEATURE, "features/rating.feature"))


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1200", "1201"), ("0", "1"), ("596.72", "597.72"), ("1.5", "2.5")],
)
def test_numbers_move_by_the_smallest_meaningful_amount(value: str, expected: str) -> None:
    assert mutation.mutate_value(value) == expected


def test_float_precision_is_preserved() -> None:
    assert mutation.mutate_value("10.00") == "11.00"


@pytest.mark.parametrize(
    ("value", "expected"), [("true", "false"), ("False", "true"), ("yes", "no"), ("off", "on")]
)
def test_booleans_flip(value: str, expected: str) -> None:
    assert mutation.mutate_value(value) == expected


def test_enums_swap_to_another_value_from_the_same_column() -> None:
    """A step treating both values alike survives noise but dies on a swap."""
    assert mutation.mutate_value("pro_rata", ["pro_rata", "short_rate"]) == "short_rate"


def test_a_string_with_no_alternative_gets_a_marker() -> None:
    assert mutation.mutate_value("only", ["only"]).startswith("only")
    assert mutation.mutate_value("only", ["only"]) != "only"


def test_empty_cells_are_still_mutated() -> None:
    assert mutation.mutate_value("") == mutation.MARKER


def test_every_mutant_changes_something() -> None:
    assert all(m.original != m.mutated for m in _mutants())


def test_example_cells_are_mutated() -> None:
    examples = [m for m in _mutants() if m.kind == mutation.KIND_EXAMPLE]
    assert {m.original for m in examples} >= {"1200", "pro_rata", "596.72", "true"}


def test_plain_scenario_literals_are_mutated() -> None:
    """Most hand-written scenarios are not outlines; table-only mutation would skip them."""
    literals = [m for m in _mutants() if m.kind == mutation.KIND_LITERAL]
    assert {m.original for m in literals} == {"1200", "182", "596.72"}


def test_outline_placeholders_are_never_mutated() -> None:
    assert all("<" not in m.original for m in _mutants())


def test_mutants_are_ordered_by_position() -> None:
    positions = [(m.line, m.column) for m in _mutants()]
    assert positions == sorted(positions)


def test_apply_changes_exactly_one_value() -> None:
    mutant = next(m for m in _mutants() if m.original == "596.72")
    mutated = mutation.apply(FEATURE, mutant)
    assert mutated != FEATURE
    assert len(mutated.splitlines()) == len(FEATURE.splitlines())
    assert mutated.count("597.72") == 1


def test_apply_leaves_every_other_line_byte_identical() -> None:
    mutant = _mutants()[0]
    before, after = FEATURE.splitlines(), mutation.apply(FEATURE, mutant).splitlines()
    differing = [i for i, (b, a) in enumerate(zip(before, after, strict=True)) if b != a]
    assert len(differing) == 1


def test_apply_survives_a_round_trip_through_the_parser() -> None:
    mutant = next(m for m in _mutants() if m.kind == mutation.KIND_EXAMPLE)
    reparsed = gherkin.parse(mutation.apply(FEATURE, mutant))
    assert reparsed.name == "Premium rating"


def test_apply_refuses_a_stale_mutant() -> None:
    """Positions are offsets: applying to edited text must fail loudly, not corrupt it."""
    mutant = _mutants()[0]
    with pytest.raises(mutation.MutationError, match="no longer contains"):
        mutation.apply("Feature: x\n" + FEATURE, mutant)


def test_sample_is_deterministic_and_bounded() -> None:
    found = _mutants()
    assert mutation.sample(found, 3, seed=1) == mutation.sample(found, 3, seed=1)
    assert len(mutation.sample(found, 3)) == 3


def test_sample_of_zero_or_more_than_available_returns_everything() -> None:
    found = _mutants()
    assert mutation.sample(found, 0) == found
    assert mutation.sample(found, 999) == found
