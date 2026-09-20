"""The gated-tree hash, the last-green record, and the stop-check skip built on them."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import config as config_mod
from gauntlet import doctor, events, tree
from gauntlet.cli import EXIT_GATE_FAILURE, EXIT_OK, app
from gauntlet.gates import base
from gauntlet.gates.base import GateResult

runner = CliRunner()

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.size]
max_function_lines = 25

[gates.complexity]
max = 6
"""

GOOD = "def add(a, b):\n    return a + b\n"
LONG_FUNCTION = "def big():\n" + "    x = 1\n" * 30
STOP_PAYLOAD = json.dumps({"hook_event_name": "Stop", "session_id": "s1"})


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git-initialised project with two gates, nothing committed."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "src" / "a.py").write_text(GOOD)
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cfg(root: Path) -> config_mod.Config:
    return config_mod.load(root)


def _line_for(root: Path, rel: str) -> str:
    return f"{hashlib.sha256((root / rel).read_bytes()).hexdigest()}  {rel}\n"


def _events(root: Path, kind: str) -> list[dict[str, Any]]:
    return [item for item in events.read(events.events_path(root)) if item["kind"] == kind]


def _record(root: Path) -> dict[str, Any] | None:
    path = tree.record_path(root)
    return json.loads(path.read_text()) if path.exists() else None


def _result(gate: str, passed: bool = True) -> GateResult:
    return GateResult(gate=gate, passed=passed, threshold=None, actual=None)


# --- the hash ------------------------------------------------------------


def test_the_hash_is_sha256_over_one_digest_and_path_line_per_file(project: Path) -> None:
    (project / "tests" / "t.py").write_text("y\n")
    expected = hashlib.sha256(
        (_line_for(project, "src/a.py") + _line_for(project, "tests/t.py")).encode()
    ).hexdigest()
    assert tree.hash_tree(project, ["src", "tests"]) == tree.TreeHash(tree=expected, files=2)


def test_a_byte_change_under_a_gated_path_moves_the_hash(project: Path) -> None:
    before = tree.measure(project, _cfg(project))
    (project / "src" / "a.py").write_text(GOOD + "\n")
    after = tree.measure(project, _cfg(project))
    assert before is not None and after is not None
    assert before.tree != after.tree
    assert before.files == after.files


def test_an_untracked_new_file_under_src_moves_the_hash(project: Path) -> None:
    before = tree.measure(project, _cfg(project))
    (project / "src" / "b.py").write_text("x = 1\n")
    after = tree.measure(project, _cfg(project))
    assert before is not None and after is not None
    assert after.files == before.files + 1
    assert before.tree != after.tree


def test_an_ignored_file_does_not_move_the_hash(project: Path) -> None:
    (project / ".gitignore").write_text("*.log\n")
    before = tree.measure(project, _cfg(project))
    (project / "src" / "debug.log").write_text("noise\n")
    assert tree.measure(project, _cfg(project)) == before


def test_a_readme_edit_does_not_move_the_hash(project: Path) -> None:
    before = tree.measure(project, _cfg(project))
    (project / "README.md").write_text("# words no gate reads\n")
    assert tree.measure(project, _cfg(project)) == before


def test_a_content_identical_rename_moves_the_hash(project: Path) -> None:
    before = tree.measure(project, _cfg(project))
    (project / "src" / "a.py").rename(project / "src" / "b.py")
    after = tree.measure(project, _cfg(project))
    assert before is not None and after is not None
    assert after.files == before.files
    assert before.tree != after.tree


def test_a_deleted_tracked_file_yields_no_hash(project: Path) -> None:
    _git(project, "add", "src/a.py")
    (project / "src" / "a.py").unlink()
    assert tree.measure(project, _cfg(project)) is None


def test_a_project_outside_git_has_no_hash(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    assert tree.measure(tmp_path, _cfg(tmp_path)) is None


def test_git_absent_means_no_hash(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(args: list[str], cwd: Path, timeout: int = 0) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, base.MISSING_TOOL_RETURNCODE, "", "no git")

    monkeypatch.setattr(tree, "run_cmd", missing)
    assert tree.measure(project, _cfg(project)) is None


def test_a_file_name_git_cannot_decode_still_leaves_the_tree_unsayable(project: Path) -> None:
    """The real `git ls-files -z` through the real `run_cmd`: no hash, and nothing raised."""
    (project / "src" / os.fsdecode(b"bad\xffname")).write_text("x = 1\n")
    assert tree._listing(project, ["src"]) is None


def test_an_empty_path_list_is_never_hashed_as_the_whole_tree(project: Path) -> None:
    assert tree.hash_tree(project, []) is None


# --- the path list -------------------------------------------------------


def test_the_path_list_covers_src_tests_and_the_protect_defaults(project: Path) -> None:
    assert tree.gated_paths(_cfg(project), project) == [
        "src",
        "tests",
        "gauntlet.toml",
        ".claude/settings.json",
        "gauntlet.lock.json",
        "pyproject.toml",
    ]


def test_the_gauntlet_directory_is_never_in_the_path_list(project: Path) -> None:
    (project / "gauntlet.toml").write_text(
        CONFIG + '\n[protect]\npaths = [".gauntlet/", ".gauntlet/events.jsonl", "gauntlet.toml"]\n'
    )
    paths = tree.gated_paths(_cfg(project), project)
    assert not any(p == ".gauntlet" or p.startswith(".gauntlet/") for p in paths)
    assert "gauntlet.toml" in paths


def test_acceptance_and_boundary_paths_enter_with_the_gates_own_defaults(project: Path) -> None:
    (project / "gauntlet.toml").write_text(
        CONFIG + '\n[gates.acceptance]\nfeatures = "specs/"\n\n[gates.boundary]\n'
    )
    paths = tree.gated_paths(_cfg(project), project)
    assert paths[2:5] == ["specs", "tests/steps", "tests/api"]
    assert paths.count("tests/steps") == 1


def test_a_gate_that_is_off_contributes_no_paths(project: Path) -> None:
    paths = tree.gated_paths(_cfg(project), project)
    assert "features" not in paths
    assert "tests/steps" not in paths


# --- the record ----------------------------------------------------------


def test_the_record_round_trips_through_the_file(project: Path) -> None:
    record = tree.GreenRecord("ab" * 32, 3, "run-1", "2026-09-14T00:00:00+00:00", "check", ["size"])
    tree.write_record(project, record)
    assert tree.read_record(project) == record
    assert sorted(json.loads(tree.record_path(project).read_text())) == [
        "at",
        "command",
        "files",
        "gates",
        "run",
        "tree",
    ]


@pytest.mark.parametrize(
    "content", ["{not json", '{"tree": "x"}', '["tree"]', '{"tree": 1, "files": "n", "run": 1}']
)
def test_a_missing_or_corrupt_record_reads_as_none(project: Path, content: str) -> None:
    assert tree.read_record(project) is None
    tree.record_path(project).parent.mkdir(exist_ok=True)
    tree.record_path(project).write_text(content)
    assert tree.read_record(project) is None


def test_wholly_green_needs_every_enabled_gate_passing_over_the_whole_tree(project: Path) -> None:
    cfg = _cfg(project)
    both = [_result("size"), _result("complexity")]
    assert tree.wholly_green(cfg, both, changed=False)
    assert not tree.wholly_green(cfg, both, changed=True)
    assert not tree.wholly_green(cfg, [_result("size")], changed=False)
    assert not tree.wholly_green(cfg, [_result("size"), _result("complexity", False)], False)


def test_an_unhashable_tree_gives_null_fields() -> None:
    assert tree.fields(None) == {"tree": None, "files": None}


# --- check -----------------------------------------------------------------


def test_a_wholly_green_check_writes_the_record_and_names_the_tree(project: Path) -> None:
    result = runner.invoke(app, ["check"])
    assert result.exit_code == EXIT_OK
    (finished,) = _events(project, events.RUN_FINISHED)
    measured = tree.measure(project, _cfg(project))
    assert measured is not None
    assert finished["tree"] == measured.tree
    assert finished["files"] == measured.files == 2
    record = _record(project)
    assert record is not None
    assert record["tree"] == measured.tree
    assert record["run"] == finished["run"]
    assert record["at"] == finished["at"]
    assert record["command"] == "check"
    assert record["gates"] == ["size", "complexity"]


def test_a_gate_subset_names_the_tree_but_writes_no_record(project: Path) -> None:
    runner.invoke(app, ["check", "--gates", "size"])
    (finished,) = _events(project, events.RUN_FINISHED)
    assert len(finished["tree"]) == 64
    assert _record(project) is None


def test_a_changed_run_names_the_tree_but_writes_no_record(project: Path) -> None:
    runner.invoke(app, ["check", "--changed"])
    (finished,) = _events(project, events.RUN_FINISHED)
    assert len(finished["tree"]) == 64
    assert _record(project) is None


def test_a_red_full_run_writes_no_record(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["check"])
    assert result.exit_code == EXIT_GATE_FAILURE
    (finished,) = _events(project, events.RUN_FINISHED)
    assert len(finished["tree"]) == 64
    assert _record(project) is None


def test_a_check_outside_git_records_a_null_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "src" / "a.py").write_text(GOOD)
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["check"]).exit_code == EXIT_OK
    (finished,) = _events(tmp_path, events.RUN_FINISHED)
    assert finished["tree"] is None
    assert finished["files"] is None
    assert _record(tmp_path) is None


# --- stop-check ------------------------------------------------------------


def test_a_matching_record_skips_every_gate_with_one_reused_event(project: Path) -> None:
    runner.invoke(app, ["check"])
    gates_before = len(_events(project, events.GATE_FINISHED))
    (finished,) = _events(project, events.RUN_FINISHED)

    result = runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)

    assert result.exit_code == EXIT_OK
    assert result.output.strip() == (
        f"gauntlet stop-check skipped: gated tree unchanged since green run "
        f"{finished['run']}, {finished['at']}"
    )
    (reused,) = _events(project, events.RUN_REUSED)
    assert reused["command"] == "stop-check"
    assert reused["tree"] == finished["tree"]
    assert reused["files"] == finished["files"]
    assert reused["reused_run"] == finished["run"]
    assert reused["reused_at"] == finished["at"]
    assert len(_events(project, events.GATE_FINISHED)) == gates_before
    assert len(_events(project, events.RUN_STARTED)) == 1  # the check's; a skip has none
    assert len(_events(project, events.RUN_FINISHED)) == 1


def test_a_skip_clears_the_sessions_attempts(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    (project / "src" / "a.py").write_text(GOOD)
    runner.invoke(app, ["check"])
    attempts = project / ".gauntlet" / "stop-attempts.json"
    assert json.loads(attempts.read_text()) == {"s1": 1}
    runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    assert json.loads(attempts.read_text()) == {}


def _green_record_then(project: Path, mutate: Any) -> Any:
    runner.invoke(app, ["check"])
    gates_before = len(_events(project, events.GATE_FINISHED))
    mutate()
    result = runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    assert _events(project, events.RUN_REUSED) == []
    assert len(_events(project, events.GATE_FINISHED)) > gates_before
    return result


def test_a_mismatching_record_runs_the_gates(project: Path) -> None:
    def edit() -> None:
        (project / "src" / "a.py").write_text(GOOD + "\n")

    assert _green_record_then(project, edit).exit_code == EXIT_OK


def test_a_corrupt_record_runs_the_gates(project: Path) -> None:
    def corrupt() -> None:
        tree.record_path(project).write_text("{half a record")

    assert _green_record_then(project, corrupt).exit_code == EXIT_OK


def test_a_record_for_a_different_gate_set_runs_the_gates(project: Path) -> None:
    def other_gates() -> None:
        stored = json.loads(tree.record_path(project).read_text())
        stored["gates"] = ["size"]
        tree.record_path(project).write_text(json.dumps(stored))

    assert _green_record_then(project, other_gates).exit_code == EXIT_OK


def test_without_git_the_gates_run(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def lose_git() -> None:
        monkeypatch.setattr(
            tree,
            "run_cmd",
            lambda args, cwd, timeout=0: subprocess.CompletedProcess(args, 127, "", ""),
        )

    assert _green_record_then(project, lose_git).exit_code == EXIT_OK


def test_no_skip_unchanged_runs_the_gates_on_a_matching_record(project: Path) -> None:
    runner.invoke(app, ["check"])
    gates_before = len(_events(project, events.GATE_FINISHED))
    result = runner.invoke(app, ["stop-check", "--no-skip-unchanged"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_OK
    assert _events(project, events.RUN_REUSED) == []
    assert len(_events(project, events.GATE_FINISHED)) > gates_before


def test_a_green_stop_check_is_bounded_in_the_log_and_writes_the_record(project: Path) -> None:
    result = runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_OK
    (started,) = _events(project, events.RUN_STARTED)
    (finished,) = _events(project, events.RUN_FINISHED)
    assert started["command"] == finished["command"] == "stop-check"
    assert started["run"] == finished["run"]
    assert started["gates"] == ["size", "complexity"]
    assert len(finished["tree"]) == 64
    record = _record(project)
    assert record is not None
    assert record["command"] == "stop-check"
    assert record["run"] == finished["run"]


def test_a_red_stop_check_is_bounded_in_the_log_but_writes_no_record(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_GATE_FAILURE
    (finished,) = _events(project, events.RUN_FINISHED)
    assert finished["passed"] is False
    assert finished["failed"] == ["size"]
    assert _record(project) is None


def test_a_lock_rejected_stop_check_emits_no_boundary_lines(project: Path) -> None:
    with base.exclusive_run(project):
        result = runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_OK
    assert "in progress" in result.output
    assert _events(project, events.RUN_STARTED) == []
    assert _events(project, events.RUN_FINISHED) == []


def test_a_lock_rejected_check_emits_no_boundary_lines(project: Path) -> None:
    with base.exclusive_run(project):
        result = runner.invoke(app, ["check"])
    assert result.exit_code == EXIT_OK
    assert "in progress" in result.output
    assert _events(project, events.RUN_STARTED) == []
    assert _events(project, events.RUN_FINISHED) == []


# --- doctor ----------------------------------------------------------------


def test_doctor_ties_git_to_the_skip_path_as_well_as_changed() -> None:
    assert "--changed" in doctor.GATES_BY_TOOL["git"]
    assert any("skip-unchanged" in need for need in doctor.GATES_BY_TOOL["git"])
