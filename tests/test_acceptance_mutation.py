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


def test_locator_is_structural_not_line_based() -> None:
    """Inserting a scenario above must not lapse every approval below it."""
    original = _mutants()
    shifted = mutation.mutants(
        gherkin.parse(
            FEATURE.replace(
                "Feature: Premium rating\n",
                "Feature: Premium rating\n\n  Scenario: filler\n    Given x\n",
            )
        )
    )
    assert {m.locator for m in original} <= {m.locator for m in shifted}


def test_locator_distinguishes_cells_in_the_same_row() -> None:
    row_mutants = [m for m in _mutants() if m.kind == mutation.KIND_EXAMPLE and m.line == 15]
    assert len({m.locator for m in row_mutants}) == len(row_mutants)


def test_changing_a_cell_freshens_only_that_row_s_locators() -> None:
    """A different example case deserves a fresh judgment — but only that case.

    Approvals for untouched rows must survive an edit elsewhere in the table,
    or every table edit would lapse every judgment in the feature.
    """
    before = {m.locator for m in _mutants()}
    after = {
        m.locator
        for m in mutation.mutants(
            gherkin.parse(FEATURE.replace("| 1200    | pro_rata", "| 9999    | pro_rata"))
        )
    }
    edited = {loc for loc in before if "1200|pro_rata" in loc}
    assert edited  # the row had mutants to begin with
    assert not edited & after  # none of its judgments carry over
    assert (before - edited) <= after  # every other row keeps its identity


def test_signature_describes_the_mutation() -> None:
    mutant = next(m for m in _mutants() if m.original == "596.72")
    assert mutant.signature == "596.72->597.72"


PREFIXES = """\
Feature: Policy numbers

  Scenario Outline: Format
    Given the policy number is "<policy_number>"
    Then the validation result is "<result>"

    Examples:
      | policy_number | result  |
      | HO-1234567    | valid   |
      | AU-1234567    | valid   |
      | XX-1234567    | invalid |
"""


def _for(text: str, original: str) -> mutation.Mutant:
    return next(m for m in mutation.mutants(gherkin.parse(text)) if m.original == original)


def test_a_swap_prefers_a_row_with_a_different_outcome() -> None:
    """HO -> AU proves nothing: both are valid. HO -> XX kills the mutant."""
    assert _for(PREFIXES, "HO-1234567").mutated == "XX-1234567"


def test_the_discriminating_choice_holds_from_every_row() -> None:
    assert _for(PREFIXES, "AU-1234567").mutated == "XX-1234567"
    assert _for(PREFIXES, "XX-1234567").mutated in {"HO-1234567", "AU-1234567"}


def test_selection_is_deterministic() -> None:
    """Mutants are ledger keys: the same table must always mutate the same way."""
    first = [(m.original, m.mutated) for m in mutation.mutants(gherkin.parse(PREFIXES))]
    second = [(m.original, m.mutated) for m in mutation.mutants(gherkin.parse(PREFIXES))]
    assert first == second


def test_a_column_with_no_discriminating_row_still_mutates() -> None:
    """When every row shares an outcome the mutant is equivalent — but still produced."""
    uniform = PREFIXES.replace("| XX-1234567    | invalid |", "| CP-1234567    | valid   |")
    assert _for(uniform, "HO-1234567").mutated in {"AU-1234567", "CP-1234567"}


def test_a_single_row_table_falls_back_to_a_marker() -> None:
    single = PREFIXES.replace(
        "      | AU-1234567    | valid   |\n      | XX-1234567    | invalid |\n", ""
    )
    assert _for(single, "HO-1234567").mutated.startswith("HO-1234567")


def test_outcome_columns_still_mutate_against_the_other_outcome() -> None:
    assert _for(PREFIXES, "invalid").mutated == "valid"
