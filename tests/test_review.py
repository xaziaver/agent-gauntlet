from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gauntlet import config as config_mod
from gauntlet import locking, registry, review, specs, status
from gauntlet.cli import app
from gauntlet.cli_support import EXIT_OK

runner = CliRunner()

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.acceptance]
features = "features/"
"""

FEATURE = "Feature: Rating\n\n  Scenario: x\n    Given an amount of 100\n"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cfg(project: Path) -> config_mod.Config:
    return config_mod.load(project)


def _items(project: Path) -> list[review.Item]:
    return [review.build_item(project, p) for p in status.pending(project, _cfg(project))]


def _keys(project: Path) -> set[str]:
    return set(registry.load(locking.lock_path(project)).entries)


def test_an_unapproved_spec_shows_its_content(project: Path) -> None:
    item = next(i for i in _items(project) if i.pending.subject.endswith(".feature"))
    assert "Scenario: x" in item.body


def test_a_modified_file_shows_a_diff(project: Path) -> None:
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    (project / "features" / "rating.feature").write_text(
        FEATURE.replace("an amount of 100", "an amount of 999")
    )
    item = next(i for i in _items(project) if i.pending.status == "modified")
    assert "-" in item.body and "+" in item.body
    assert "999" in item.body


def test_a_diff_without_git_history_says_so(tmp_path: Path) -> None:
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "a.feature").write_text(FEATURE)
    body = review.diff_against_head(tmp_path, "features/a.feature")
    assert "inspect the file directly" in body


def test_a_deleted_subject_is_explained(project: Path) -> None:
    assert "no longer exists" in review.diff_against_head(project, "features/gone.feature")


def test_approving_one_item_leaves_the_others_pending(project: Path) -> None:
    """approve_all replaces the namespace; review must not drop what it did not touch."""
    before = len(_items(project))
    item = _items(project)[0]
    registry.save(review.apply(project, item, "", "me"), locking.lock_path(project))
    assert len(_items(project)) == before - 1


def test_approving_config_paths_one_at_a_time_accumulates(project: Path) -> None:
    first = locking.approve_paths(project, ["gauntlet.toml"])
    registry.save(first, locking.lock_path(project))
    second = locking.approve_paths(project, ["pyproject.toml"])
    assert "config:gauntlet.toml" in second.entries


def test_review_with_an_empty_inbox_says_so(project: Path) -> None:
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    result = runner.invoke(app, ["review"])
    assert result.exit_code == EXIT_OK
    assert "nothing needs your approval" in result.output


def test_skipping_everything_approves_nothing(project: Path) -> None:
    before = _keys(project)
    result = runner.invoke(app, ["review"], input="s\ns\ns\n")
    assert result.exit_code == EXIT_OK
    assert _keys(project) == before
    assert "approved 0 of" in result.output


def test_quitting_stops_the_walk(project: Path) -> None:
    result = runner.invoke(app, ["review"], input="q\n")
    assert "approved 0 of" in result.output


def test_approving_records_the_reviewer_and_clears_the_item(project: Path) -> None:
    result = runner.invoke(app, ["review", "--yes", "--reviewer", "xaziaver"])
    assert result.exit_code == EXIT_OK
    assert _keys(project)
    assert status.pending(project, _cfg(project)) == []


def test_an_invalid_answer_reprompts(project: Path) -> None:
    result = runner.invoke(app, ["review"], input="x\nq\n")
    assert "Please answer" in result.output


def test_the_reviewer_is_recorded_on_a_config_approval(project: Path) -> None:
    """--reviewer was accepted and silently dropped before this."""
    runner.invoke(app, ["review", "--yes", "--reviewer", "xaziaver"])
    entries = registry.load(locking.lock_path(project)).entries
    assert any(e.reviewer == "xaziaver" for e in entries.values())


def test_a_modified_item_requires_a_reason(project: Path) -> None:
    """A changed threshold or spec is the one thing a future reader asks 'why?' about."""
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    (project / "features" / "rating.feature").write_text(FEATURE.replace("100", "999"))

    items = _items(project)
    assert [i.pending.status for i in items] == ["modified"]

    runner.invoke(app, ["review"], input="a\nbecause the rule changed\n")
    entries = registry.load(locking.lock_path(project)).entries
    assert entries["spec:features/rating.feature"].reason == "because the rule changed"
