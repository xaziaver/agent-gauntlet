from __future__ import annotations

import pytest

from gauntlet.acceptance import gherkin

FEATURE = """\
# a comment
@rating @slow
Feature: Premium rating

  Some narrative prose that is not part of the IR.

  Background:
    Given a policy term of 12 months

  @pro-rata
  Scenario: Pro-rata cancellation
    Given an annual premium of 1200
    When the policy is cancelled after 182 days
    Then the earned premium is 596.72

  Scenario Outline: Short-rate penalty
    Given an annual premium of <premium>
    When the policy is cancelled after <days> days
    Then the earned premium is <earned>

    Examples:
      | premium | days | earned |
      | 1200    | 182  | 657.05 |
      | 2400    | 90   | 700.00 |
"""


def test_feature_name_and_tags() -> None:
    feature = gherkin.parse(FEATURE, "features/rating.feature")
    assert feature.name == "Premium rating"
    assert feature.tags == ["@rating", "@slow"]
    assert feature.path == "features/rating.feature"


def test_background_steps_are_separate_from_scenarios() -> None:
    feature = gherkin.parse(FEATURE)
    assert [s.text for s in feature.background] == ["a policy term of 12 months"]
    assert all("policy term" not in s.text for sc in feature.scenarios for s in sc.steps)


def test_scenarios_are_parsed_with_keywords_and_lines() -> None:
    feature = gherkin.parse(FEATURE)
    assert [s.name for s in feature.scenarios] == ["Pro-rata cancellation", "Short-rate penalty"]
    first = feature.scenarios[0]
    assert [s.keyword for s in first.steps] == ["Given", "When", "Then"]
    assert first.steps[0].line == 12


def test_scenario_tags_do_not_leak_to_the_next_scenario() -> None:
    feature = gherkin.parse(FEATURE)
    assert feature.scenarios[0].tags == ["@pro-rata"]
    assert feature.scenarios[1].tags == []


def test_outline_is_flagged_and_carries_its_table() -> None:
    outline = gherkin.parse(FEATURE).scenarios[1]
    assert outline.is_outline is True
    assert outline.examples is not None
    assert outline.examples.headers == ["premium", "days", "earned"]
    assert [r.values for r in outline.examples.rows] == [
        ["1200", "182", "657.05"],
        ["2400", "90", "700.00"],
    ]


def test_plain_scenario_has_no_examples() -> None:
    assert gherkin.parse(FEATURE).scenarios[0].examples is None


def test_cell_columns_locate_the_value_in_its_line() -> None:
    """Mutation edits the source text in place, so these offsets must be exact."""
    feature = gherkin.parse(FEATURE)
    row = feature.scenarios[1].examples.rows[0]
    line = FEATURE.splitlines()[row.line - 1]
    for cell in row.cells:
        assert line[cell.column : cell.column + len(cell.value)] == cell.value


def test_split_row_handles_padding_and_empty_cells() -> None:
    row = gherkin.split_row("|  a |    | b|", 7)
    assert row.values == ["a", "", "b"]
    assert row.line == 7


def test_comments_and_prose_are_ignored() -> None:
    feature = gherkin.parse(FEATURE)
    assert all("narrative" not in s.text for sc in feature.scenarios for s in sc.steps)


def test_missing_feature_declaration_is_an_error() -> None:
    with pytest.raises(gherkin.GherkinError, match="no Feature:"):
        gherkin.parse("Scenario: orphan\n  Given nothing\n")


def test_step_outside_a_scenario_is_an_error() -> None:
    with pytest.raises(gherkin.GherkinError, match="outside a scenario"):
        gherkin.parse("Feature: x\n  Given a step with no scenario\n")


def test_examples_alias_scenarios_keyword_is_accepted() -> None:
    text = FEATURE.replace("Examples:", "Scenarios:")
    assert gherkin.parse(text).scenarios[1].examples is not None


def test_step_columns_locate_the_text_in_its_line() -> None:
    feature = gherkin.parse(FEATURE)
    step = feature.scenarios[0].steps[0]
    line = FEATURE.splitlines()[step.line - 1]
    assert line[step.column : step.column + len(step.text)] == step.text
