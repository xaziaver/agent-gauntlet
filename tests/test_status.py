from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet import config as config_mod
from gauntlet import events, locking, registry, specs, status, status_render
from gauntlet.gates.base import GateResult

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.acceptance]
features = "features/"
"""

FEATURE = "Feature: Rating\n\n  Scenario: x\n    Given y\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    return tmp_path


def _cfg(project: Path) -> config_mod.Config:
    return config_mod.load(project)


def test_an_unlocked_project_reports_config_and_specs_as_pending(project: Path) -> None:
    items = status.pending(project, _cfg(project))
    assert {i.namespace for i in items} == {locking.CONFIG_NAMESPACE, specs.SPEC_NAMESPACE}
    assert all(i.status == "unapproved" for i in items)


def test_locking_clears_the_config_items(project: Path) -> None:
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    items = status.pending(project, _cfg(project))
    assert {i.namespace for i in items} == {specs.SPEC_NAMESPACE}


def test_approving_everything_empties_the_inbox(project: Path) -> None:
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    assert status.pending(project, _cfg(project)) == []


def test_an_edited_spec_reappears_in_the_inbox(project: Path) -> None:
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    (project / "features" / "rating.feature").write_text(FEATURE + "    And z\n")
    items = status.pending(project, _cfg(project))
    assert any(i.status == "modified" for i in items)


def test_each_item_names_the_command_that_clears_it(project: Path) -> None:
    """The inbox is useless if it does not say what to do about an entry."""
    items = status.pending(project, _cfg(project))
    config_item = next(i for i in items if i.namespace == locking.CONFIG_NAMESPACE)
    spec_item = next(i for i in items if i.namespace == specs.SPEC_NAMESPACE)
    assert config_item.action == "gauntlet lock"
    assert "features/rating.feature" in spec_item.action


def test_a_project_without_specs_reports_none(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    items = status.pending(tmp_path, config_mod.load(tmp_path))
    assert all(i.namespace == locking.CONFIG_NAMESPACE for i in items)


def test_collect_gathers_gates_pending_and_activity(project: Path) -> None:
    events.Log(project, run="r1").emit(events.RUN_STARTED, command="check")
    gates = [GateResult(gate="size", passed=True, threshold=25, actual=10)]
    current = status.collect(project, _cfg(project), gates)
    assert current.passed is True
    assert current.locked is False
    assert current.pending
    assert current.recent[0]["kind"] == events.RUN_STARTED


def test_status_without_gates_is_not_reported_as_passing(project: Path) -> None:
    """No run is not the same as a clean run."""
    assert status.collect(project, _cfg(project)).passed is False


def test_the_json_shape_is_stable(project: Path) -> None:
    payload = status.collect(project, _cfg(project)).to_dict()
    assert set(payload) == {"passed", "locked", "gates", "pending", "recent"}
    assert set(payload["pending"][0]) == {"namespace", "subject", "status", "action"}


def test_render_says_so_when_the_gates_have_not_run(project: Path) -> None:
    text = status_render.render(status.collect(project, _cfg(project)))
    assert "not run" in text


def test_render_shows_an_empty_inbox_positively(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "gauntlet.toml").write_text(
        "[project]\nlanguage = 'python'\nsrc = 'src/'\ntests = 'tests/'\n"
    )
    cfg = config_mod.load(tmp_path)
    updated, _ = locking.approve_all(tmp_path, cfg.verified_paths)
    registry.save(updated, locking.lock_path(tmp_path))
    text = status_render.render(status.collect(tmp_path, cfg))
    assert "nothing needs your approval" in text


def test_a_long_error_is_reduced_to_one_short_line() -> None:
    failing = GateResult(
        gate="tests",
        passed=False,
        threshold="x",
        actual=None,
        error="pytest exited 2: ERRORS\n" + "traceback line\n" * 50,
    )
    line = status_render._detail(failing)
    assert "\n" not in line
    assert len(line) < 90


def test_spinner_frames_are_skipped_to_reach_the_real_message() -> None:
    """Tools write progress and errors to the same stream."""
    noisy = "⠋ Generating mutants\n⠙ Generating mutants\nFileNotFoundError: boom\n"
    assert "FileNotFoundError" in status_render._first_meaningful_line(noisy)


def test_dict_actuals_render_readably() -> None:
    gate = GateResult(gate="coverage", passed=True, threshold={}, actual={"line": 100.0})
    assert status_render._detail(gate) == "line=100.0"


def test_render_shows_all_three_sections(project: Path) -> None:
    gates = [GateResult(gate="size", passed=False, threshold=25, actual=30)]
    text = status_render.render(status.collect(project, _cfg(project), gates))
    assert "GATES     FAILING" in text
    assert "WAITING" in text
    assert "ACTIVITY" in text
    assert "gauntlet check" in text  # a failing summary points at the full report


def test_output_that_is_only_spinner_frames_still_returns_something() -> None:
    assert status_render._first_meaningful_line("⠋ Generating\n⠙ Generating\n").strip()
