"""CLI tests for `gauntlet mutant`: classifying survivors is a human judgment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import locking, registry, specs
from gauntlet import mutants as mutants_mod
from gauntlet.cli import app
from gauntlet.cli_support import EXIT_CONFIG_ERROR, EXIT_OK

runner = CliRunner()

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.acceptance]
features = "features/"
steps = "tests/steps"
"""

FEATURE = """\
Feature: Tiering

  Scenario Outline: Amount decides the tier
    Given an amount of <amount>
    Then the tier is "<tier>"

    Examples:
      | amount | tier     |
      | 75000  | high     |
      | 100    | standard |
"""

RATING = 'def tier(amount: int) -> str:\n    return "high" if amount > 50000 else "standard"\n'

CONFTEST = (
    "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent / 'src'))\n"
)

BINDINGS = """\
from pytest_bdd import given, parsers, scenarios, then

from rating import tier

scenarios("../../features/tiering.feature")


@given(parsers.parse("an amount of {amount:d}"), target_fixture="amount")
def _amount(amount: int) -> int:
    return amount


@then(parsers.parse('the tier is "{expected}"'))
def _check(amount: int, expected: str) -> None:
    assert tier(amount) == expected
"""


def _text(result: Any) -> str:
    if result.output.strip():
        return result.output
    try:
        return result.stderr or ""
    except ValueError:
        return ""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "features").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "tiering.feature").write_text(FEATURE)
    (tmp_path / "src" / "rating.py").write_text(RATING)
    (tmp_path / "conftest.py").write_text(CONFTEST)
    (tmp_path / "tests" / "steps" / "test_tiering.py").write_text(BINDINGS)
    updated = specs.approve(tmp_path, [tmp_path / "features" / "tiering.feature"])
    registry.save(updated, locking.lock_path(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _mutant_keys(project: Path) -> set[str]:
    approved = registry.load(locking.lock_path(project))
    return set(registry.in_namespace(approved, mutants_mod.MUTANT_NAMESPACE).entries)


def test_approve_records_the_surviving_mutants(project: Path) -> None:
    """75000 -> 75001 is still 'high': the spec cannot distinguish them."""
    result = runner.invoke(
        app,
        ["mutant", "approve", "features/tiering.feature", "--reason", "same tier either side"],
    )
    assert result.exit_code == EXIT_OK
    assert _mutant_keys(project)


def test_approve_requires_a_reason(project: Path) -> None:
    result = runner.invoke(app, ["mutant", "approve", "features/tiering.feature"])
    assert result.exit_code != EXIT_OK


def test_approve_rejects_a_missing_feature(project: Path) -> None:
    result = runner.invoke(app, ["mutant", "approve", "features/nope.feature", "--reason", "x"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_approved_survivors_stop_failing_the_gate(project: Path) -> None:
    before = runner.invoke(app, ["check", "--gates", "acceptance"])
    assert before.exit_code != EXIT_OK
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "equivalent"])
    after = runner.invoke(app, ["check", "--gates", "acceptance"])
    assert after.exit_code == EXIT_OK
    assert "reviewed-equivalent" in _text(after)


def test_list_shows_the_reason_and_reviewer(project: Path) -> None:
    runner.invoke(
        app,
        [
            "mutant",
            "approve",
            "features/tiering.feature",
            "--reason",
            "both map to high",
            "--reviewer",
            "xaziaver",
        ],
    )
    listed = _text(runner.invoke(app, ["mutant", "list"]))
    assert "both map to high" in listed
    assert "xaziaver" in listed


def test_scenario_filter_narrows_the_approval(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "mutant",
            "approve",
            "features/tiering.feature",
            "--reason",
            "x",
            "--scenario",
            "No such scenario",
        ],
    )
    assert result.exit_code == EXIT_OK
    assert "no surviving mutants" in _text(result)
    assert not _mutant_keys(project)


def test_prune_reports_nothing_when_every_approval_still_applies(project: Path) -> None:
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    result = runner.invoke(app, ["mutant", "prune", "features/tiering.feature"])
    assert result.exit_code == EXIT_OK
    assert "no stale approvals" in _text(result)


def test_prune_removes_only_the_approval_that_no_longer_survives(project: Path) -> None:
    """Tightening one case lapses its judgment; judgments about other cases stand."""
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    assert len(_mutant_keys(project)) == 2

    # 50000 -> 50001 now crosses the threshold, so that mutant dies and its
    # approval is stale. The untouched row is unaffected.
    (project / "features" / "tiering.feature").write_text(
        FEATURE.replace("| 75000  | high     |", "| 50000  | standard |")
    )
    updated = specs.approve(project, [project / "features" / "tiering.feature"])
    registry.save(updated, locking.lock_path(project))

    runner.invoke(app, ["mutant", "prune", "features/tiering.feature"])
    remaining = _mutant_keys(project)
    assert len(remaining) == 1
    assert not any("75000" in key for key in remaining)
    assert any("100|standard" in key for key in remaining)
