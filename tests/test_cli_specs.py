"""CLI tests for the spec sub-app: approval is the human's ceremony."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import locking, registry
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
"""

FEATURE = "Feature: Rating\n\n  Scenario: annual\n    Given a monthly premium of 100\n"


def _text(result: Any) -> str:
    if result.output.strip():
        return result.output
    try:
        return result.stderr or ""
    except ValueError:
        return ""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features" / "nested").mkdir(parents=True)
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    (tmp_path / "features" / "nested" / "claims.feature").write_text(FEATURE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _entries(project: Path) -> set[str]:
    return set(registry.load(locking.lock_path(project)).entries)


def test_approve_records_the_spec_and_reports_it(project: Path) -> None:
    result = runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    assert result.exit_code == EXIT_OK
    assert "approved  features/rating.feature" in _text(result)
    assert _entries(project) == {"spec:features/rating.feature"}


def test_approve_accepts_several_specs_at_once(project: Path) -> None:
    result = runner.invoke(
        app,
        ["spec", "approve", "features/rating.feature", "features/nested/claims.feature"],
    )
    assert result.exit_code == EXIT_OK
    assert _entries(project) == {
        "spec:features/rating.feature",
        "spec:features/nested/claims.feature",
    }


def test_approving_one_spec_leaves_earlier_approvals_alone(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    runner.invoke(app, ["spec", "approve", "features/nested/claims.feature"])
    assert len(_entries(project)) == 2


def test_approve_does_not_disturb_the_config_namespace(project: Path) -> None:
    """One ledger, several namespaces: approving a spec must not drop config approvals."""
    runner.invoke(app, ["lock"])
    config_keys = {k for k in _entries(project) if k.startswith("config:")}
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    assert config_keys <= _entries(project)


def test_re_approving_after_an_edit_updates_the_hash(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    before = registry.load(locking.lock_path(project)).entries["spec:features/rating.feature"]
    (project / "features" / "rating.feature").write_text(FEATURE + "    And a term of 12 months\n")
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    after = registry.load(locking.lock_path(project)).entries["spec:features/rating.feature"]
    assert before.digest != after.digest


def test_approve_of_a_missing_spec_exits_one(project: Path) -> None:
    result = runner.invoke(app, ["spec", "approve", "features/nope.feature"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "no such spec" in _text(result)


def test_approve_outside_a_project_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_list_marks_every_discovered_spec_unapproved_at_first(project: Path) -> None:
    result = runner.invoke(app, ["spec", "list"])
    assert result.exit_code == EXIT_OK
    text = _text(result)
    assert "unapproved" in text
    assert "features/rating.feature" in text
    assert "features/nested/claims.feature" in text


def test_list_marks_an_approved_spec(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    lines = {
        line.split()[1]: line.split()[0]
        for line in _text(runner.invoke(app, ["spec", "list"])).splitlines()
        if line.strip()
    }
    assert lines["features/rating.feature"] == "approved"
    assert lines["features/nested/claims.feature"] == "unapproved"


def test_list_marks_an_edited_spec_modified(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    (project / "features" / "rating.feature").write_text(FEATURE + "    And more\n")
    assert "modified" in _text(runner.invoke(app, ["spec", "list"]))


def test_list_reports_an_approved_spec_that_was_deleted(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    (project / "features" / "rating.feature").unlink()
    assert "missing" in _text(runner.invoke(app, ["spec", "list"]))


def test_list_with_no_specs_says_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["spec", "list"])
    assert result.exit_code == EXIT_OK
    assert _text(result).strip() == ""
