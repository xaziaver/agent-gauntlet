from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gauntlet import config as config_mod
from gauntlet import events, locking, mutants, registry, specs, status, status_render
from gauntlet.acceptance import survivors
from gauntlet.acceptance.mutation import KIND_EXAMPLE, Mutant
from gauntlet.cli import app
from gauntlet.gates.base import GateResult
from tests import test_cli_mutants as tiering

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
    assert set(payload) == {"passed", "locked", "gates", "pending", "recent", "disabled"}
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


def test_status_names_gates_that_are_not_enabled(project: Path) -> None:
    current = status.collect(project, _cfg(project))
    assert "mutation" in current.disabled
    assert "mutation" in status_render.render(current)


# --- mutants, from the record the acceptance gate writes -------------------------

KEY = "features/rating.feature"
SEVEN = Mutant("x", 4, 12, "7", "8", KIND_EXAMPLE, "n|7")
NINE = Mutant("x", 5, 12, "9", "10", KIND_EXAMPLE, "n|9")


def _settled(project: Path) -> None:
    """Config locked and the spec approved: only mutants can be pending."""
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    registry.save(specs.approve(project, [project / KEY]), locking.lock_path(project))


def _recorded(project: Path, *found: Mutant) -> None:
    spec = registry.digest((project / KEY).read_bytes())
    survivors.write(project, {KEY: survivors.Measured(spec=spec, survivors=list(found))})


def _mutant_items(project: Path) -> list[tuple[str, str]]:
    return [
        (i.subject, i.status)
        for i in status.pending(project, _cfg(project))
        if i.namespace == mutants.MUTANT_NAMESPACE
    ]


def test_pending_lists_unreviewed_survivors_from_the_record(project: Path) -> None:
    _settled(project)
    _recorded(project, SEVEN, NINE)
    assert _mutant_items(project) == [
        ("features/rating.feature#x|example|n|7", "unapproved"),
        ("features/rating.feature#x|example|n|9", "unapproved"),
    ]
    assert [i.namespace for i in status.pending(project, _cfg(project))] == ["mutant"] * 2


def test_pending_orders_config_then_spec_then_mutants_in_record_order(project: Path) -> None:
    _recorded(project, NINE, SEVEN)  # nothing approved: config and spec are pending too
    items = status.pending(project, _cfg(project))
    namespaces = [i.namespace for i in items]
    assert namespaces[-3:] == ["spec", "mutant", "mutant"]
    assert namespaces[:-3] and set(namespaces[:-3]) == {"config"}
    assert [i.subject for i in items[-2:]] == [mutants.key_for(KEY, m) for m in (NINE, SEVEN)]


def test_pending_classifies_the_record_against_the_current_ledger(project: Path) -> None:
    """The record is unclassified; the ledger of the moment decides what is pending."""
    _settled(project)
    _recorded(project, SEVEN, NINE)
    lock = locking.lock_path(project)
    registry.save(mutants.approve(project, KEY, [SEVEN], reason="same outcome"), lock)
    re_aimed = registry.namespaced(mutants.MUTANT_NAMESPACE, mutants.key_for(KEY, NINE))
    registry.save(registry.approve(registry.load(lock), re_aimed, b"9->99"), lock)
    assert _mutant_items(project) == [("features/rating.feature#x|example|n|9", "modified")]


def test_pending_hides_survivors_whose_spec_changed_since_the_record(project: Path) -> None:
    _settled(project)
    _recorded(project, SEVEN)
    (project / KEY).write_text(FEATURE + "    And z\n")
    items = status.pending(project, _cfg(project))
    assert [(i.namespace, i.subject, i.status) for i in items] == [("spec", KEY, "modified")]


def test_pending_hides_survivors_of_a_spec_that_no_longer_exists(project: Path) -> None:
    _settled(project)
    _recorded(project, SEVEN)
    (project / KEY).unlink()
    assert _mutant_items(project) == []


def test_pending_without_a_record_excludes_mutants_as_before(project: Path) -> None:
    _settled(project)
    assert not (project / survivors.RECORD).exists()
    assert status.pending(project, _cfg(project)) == []


@pytest.mark.parametrize(
    "item",
    [{"scenario": "x"}, {**dataclasses.asdict(SEVEN), "extra": 1}, "not an object"],
    ids=["missing-fields", "unknown-field", "not-an-object"],
)
def test_a_survivor_that_does_not_rebuild_makes_the_record_no_record(
    project: Path, item: object
) -> None:
    """One bad item and the whole record is unread: no partial inbox, and no crash."""
    _settled(project)
    _recorded(project, SEVEN)
    path = project / survivors.RECORD
    record = json.loads(path.read_text())
    record[KEY]["survivors"].append(item)
    path.write_text(json.dumps(record))
    assert status.pending(project, _cfg(project)) == []


def test_a_feature_entry_without_its_fields_makes_the_record_no_record(project: Path) -> None:
    _settled(project)
    (project / ".gauntlet").mkdir()
    (project / survivors.RECORD).write_text(json.dumps({KEY: {"survivors": []}}))
    assert status.pending(project, _cfg(project)) == []


def test_a_pending_mutant_serialises_with_its_key_status_and_action(project: Path) -> None:
    _settled(project)
    _recorded(project, SEVEN)
    payload = status.collect(project, _cfg(project)).to_dict()
    assert payload["pending"] == [
        {
            "namespace": "mutant",
            "subject": "features/rating.feature#x|example|n|7",
            "status": "unapproved",
            "action": "gauntlet review",
        }
    ]


@pytest.fixture
def tiering_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real pytest-bdd project whose two outline rows each leave a mutant alive."""
    (tmp_path / "features").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    (tmp_path / "gauntlet.toml").write_text(tiering.CONFIG)
    (tmp_path / "features" / "tiering.feature").write_text(tiering.FEATURE)
    (tmp_path / "src" / "rating.py").write_text(tiering.RATING)
    (tmp_path / "conftest.py").write_text(tiering.CONFTEST)
    (tmp_path / "tests" / "steps" / "test_tiering.py").write_text(tiering.BINDINGS)
    updated, _ = locking.approve_all(tmp_path, config_mod.load(tmp_path).verified_paths)
    registry.save(updated, locking.lock_path(tmp_path))
    registry.save(
        specs.approve(tmp_path, [tmp_path / "features" / "tiering.feature"]),
        locking.lock_path(tmp_path),
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_status_run_lists_the_survivors_it_just_counted(tiering_project: Path) -> None:
    """No record before the run: the gate writes it, then the inbox reads it."""
    assert not (tiering_project / survivors.RECORD).exists()
    result = CliRunner().invoke(app, ["status", "--run"])
    assert result.exit_code == 0
    out = result.output
    assert "✗ acceptance   1 spec(s), 2 surviving mutant(s)" in out
    assert "nothing needs your approval" not in out
    assert "WAITING   2 item(s) need your approval" in out
    waiting = out[out.index("WAITING") :]
    for row in ("75000|high", "100|standard"):
        line = f"unapproved  features/tiering.feature#Amount decides the tier|example|amount|{row}"
        assert line in waiting
    assert waiting.count("-> gauntlet review") == 2
    assert out.index("✗ acceptance") < out.index("WAITING")


def test_a_missing_spec_names_the_unapprove_command(project: Path) -> None:
    """A missing config path still names `gauntlet lock`, which clears it; an
    unapproved spec still names `gauntlet spec approve`."""
    gone = project / "features" / "gone.feature"
    (project / "pyproject.toml").write_text('[project]\nname = "x"\n')
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    gone.write_text(FEATURE)
    registry.save(specs.approve(project, [gone]), locking.lock_path(project))
    gone.unlink()
    (project / "pyproject.toml").unlink()
    items = [(i.subject, i.status, i.action) for i in status.pending(project, _cfg(project))]
    assert items == [
        ("pyproject.toml", "missing", "gauntlet lock"),
        ("features/gone.feature", "missing", "gauntlet spec unapprove features/gone.feature"),
        ("features/rating.feature", "unapproved", "gauntlet spec approve features/rating.feature"),
    ]
