"""Integration tests for the acceptance gate, against a real pytest-bdd project.

This fixture is also the reference layout: features/ at the root, bindings under
tests/steps/, and production code reached through an import the bindings own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet import locking, registry, specs
from gauntlet.gates import acceptance
from gauntlet.gates.base import GateContext

FEATURE = """\
Feature: Premium rating

  Scenario: Annual premium
    Given a monthly premium of 100
    Then the annual premium is 1200

  Scenario Outline: Terms
    Given a monthly premium of <monthly>
    Then the annual premium is <annual>

    Examples:
      | monthly | annual |
      | 50      | 600    |
      | 200     | 2400   |
"""

RATING = "def annual(monthly: int) -> int:\n    return monthly * 12\n"

CONFTEST = (
    "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent / 'src'))\n"
)

BINDINGS = """\
from pytest_bdd import given, parsers, scenarios, then

from rating import annual

scenarios("../../features/rating.feature")


@given(parsers.parse("a monthly premium of {amount:d}"), target_fixture="monthly")
def _monthly(amount: int) -> int:
    return amount


@then(parsers.parse("the annual premium is {expected:d}"))
def _check(monthly: int, expected: int) -> None:
    assert annual(monthly) == expected
"""

DECORATIVE = """\
from pytest_bdd import given, parsers, scenarios, then

scenarios("../../features/rating.feature")


@given(parsers.parse("a monthly premium of {amount:d}"), target_fixture="monthly")
def _monthly(amount: int) -> int:
    return amount


@then(parsers.parse("the annual premium is {expected:d}"))
def _check(monthly: int, expected: int) -> None:
    assert True  # asserts nothing about the values the spec claims to test
"""

CONFIG = {"features": "features/", "steps": "tests/steps", "mutation_sample": 2}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "features").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    (tmp_path / "src" / "rating.py").write_text(RATING)
    (tmp_path / "conftest.py").write_text(CONFTEST)
    (tmp_path / "tests" / "steps" / "test_rating.py").write_text(BINDINGS)
    return tmp_path


def _ctx(root: Path) -> GateContext:
    return GateContext(project_root=root, src=root / "src", tests=root / "tests")


def _approve(root: Path) -> None:
    updated = specs.approve(root, [root / "features" / "rating.feature"])
    registry.save(updated, locking.lock_path(root))


def test_no_features_passes_vacuously(tmp_path: Path) -> None:
    """Adoption must not break a project that has no specs yet."""
    result = acceptance.run(_ctx(tmp_path), CONFIG)
    assert result.passed is True
    assert result.actual == "no feature files"


def test_unapproved_spec_fails_before_anything_runs(project: Path) -> None:
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert result.diagnostics[0].symbol == "unapproved"
    assert "features/rating.feature" in result.diagnostics[0].file


def test_approved_and_bound_spec_passes(project: Path) -> None:
    _approve(project)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is True, result.diagnostics


def test_an_edited_approved_spec_fails(project: Path) -> None:
    """The core protection: an agent cannot rewrite the spec to match its code."""
    _approve(project)
    (project / "features" / "rating.feature").write_text(
        FEATURE.replace("the annual premium is 1200", "the annual premium is 999")
    )
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert result.diagnostics[0].symbol == "modified"
    assert "spec is the human's artifact" in result.diagnostics[0].message


def test_failing_scenarios_fail_the_gate(project: Path) -> None:
    _approve(project)
    (project / "src" / "rating.py").write_text("def annual(monthly: int) -> int:\n    return 0\n")
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert "scenarios failing" in str(result.actual)


def test_decorative_scenarios_are_caught_by_mutation(project: Path) -> None:
    """Bindings that assert nothing pass the suite — only mutation exposes them."""
    _approve(project)
    (project / "tests" / "steps" / "test_rating.py").write_text(DECORATIVE)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert "surviving mutant" in str(result.actual)
    assert "still passes with this value changed" in result.diagnostics[0].message


def test_mutation_restores_the_feature_file(project: Path) -> None:
    """A mutant is a temporary in-place edit; the human's artifact must survive it."""
    _approve(project)
    before = (project / "features" / "rating.feature").read_text()
    acceptance.run(_ctx(project), CONFIG)
    assert (project / "features" / "rating.feature").read_text() == before


def test_mutation_can_be_disabled(project: Path) -> None:
    _approve(project)
    (project / "tests" / "steps" / "test_rating.py").write_text(DECORATIVE)
    result = acceptance.run(_ctx(project), {**CONFIG, "mutate_examples": False})
    assert result.passed is True
    assert "passing" in str(result.actual)


def test_approval_can_be_disabled_for_adoption(project: Path) -> None:
    result = acceptance.run(_ctx(project), {**CONFIG, "require_approved": False})
    assert result.passed is True
