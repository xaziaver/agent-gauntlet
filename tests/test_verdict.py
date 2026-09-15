"""The committed verdict record: `check --record`, `verdict export`, digest and harness."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import __version__, events, tree, verdict
from gauntlet import config as config_mod
from gauntlet.cli import EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE, EXIT_OK, app
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

ARCHIVE_RUN = "20260911T110451-2238600"
ARCHIVE = Path(__file__).parent / "fixtures" / f"prototype-1-run-{ARCHIVE_RUN}.jsonl"
ARCHIVE_DIGEST = "9c7aececf56dc4f5214bfc4a07cd729f347086039dc7ba9193c6edfa3d01ca42"

ENVELOPE = ("v", "at", "run", "kind")
VOLATILE = ("run", "at", "duration")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A git-initialised project under `tmp_path/proj`, so `tmp_path` itself is outside it."""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "gauntlet.toml").write_text(CONFIG)
    (root / "src" / "a.py").write_text(GOOD)
    _git(root, "init", "-q")
    monkeypatch.chdir(root)
    return root


def _text(result: Any) -> str:
    return result.output if result.output.strip() else (result.stderr or "")


def _log(root: Path) -> list[dict[str, Any]]:
    return events.read(events.events_path(root))


def _events(root: Path, kind: str) -> list[dict[str, Any]]:
    return [item for item in _log(root) if item["kind"] == kind]


def _read(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def _payload(line: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in line.items() if key not in ENVELOPE}


def _stable(line: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in line.items() if key not in VOLATILE}


def _result(gate: str, actual: Any, passed: bool = True) -> GateResult:
    return GateResult(gate=gate, passed=passed, threshold=None, actual=actual)


def _lines_of(gate_results: list[GateResult]) -> list[dict[str, Any]]:
    return [
        {
            "gate": r.gate,
            "passed": r.passed,
            "actual": r.actual,
            "duration": r.duration,
            "diagnostics": len(r.diagnostics),
            "error": r.error,
        }
        for r in gate_results
    ]


# --- check --record ----------------------------------------------------------


def test_a_record_carries_the_runs_gate_finished_lines_verbatim(
    project: Path, tmp_path: Path
) -> None:
    out = tmp_path / "verdict.json"
    assert runner.invoke(app, ["check", "--record", str(out)]).exit_code == EXIT_OK
    (finished,) = _events(project, events.RUN_FINISHED)
    lines = _events(project, events.GATE_FINISHED)
    record = _read(out)
    assert record["run"] == finished["run"]
    assert record["verdict"] == [_payload(line) for line in lines]
    assert [line["gate"] for line in record["verdict"]] == ["size", "complexity"]
    assert record["verdict_sha256"] == verdict.digest([_payload(line) for line in lines])
    assert record["passed"] is True
    assert record["v"] == 1
    assert record["command"] == "check"
    assert record["changed"] is False
    assert record["gates"] == ["size", "complexity"]
    assert record["finished_at"] == finished["at"]
    assert record["tree"] == finished["tree"]
    assert record["files"] == finished["files"] == 2
    assert out.read_text(encoding="utf-8") == json.dumps(record, indent=2, sort_keys=True) + "\n"


def test_a_record_of_an_unlogged_run_has_a_null_finished_at_and_the_logs_run_id(
    project: Path,
) -> None:
    run = tree.Invocation(project, config_mod.load(project), "check", measured=None)
    record = verdict.from_run([_result("size", 3)], run, ["size"], None, "run-x")
    assert record.run == "run-x"
    assert record.finished_at is None
    assert record.tree is None and record.files is None


def test_record_refuses_a_path_under_dot_gauntlet_before_any_gate_runs(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_yet(root: Path, cfg: Any) -> None:
        raise AssertionError("the tree was hashed before the path was refused")

    monkeypatch.setattr(tree, "measure", not_yet)
    result = runner.invoke(app, ["check", "--record", ".gauntlet/verdict.json"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "'.gauntlet'" in _text(result)
    assert not (project / ".gauntlet" / "verdict.json").exists()
    assert _log(project) == []


def test_record_refuses_a_path_under_a_gated_path_before_any_gate_runs(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def not_yet(root: Path, cfg: Any) -> None:
        raise AssertionError("the tree was hashed before the path was refused")

    monkeypatch.setattr(tree, "measure", not_yet)
    result = runner.invoke(app, ["check", "--record", str(project / "src" / "verdict.json")])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "'src'" in _text(result)
    assert not (project / "src" / "verdict.json").exists()
    assert _log(project) == []


def test_record_accepts_a_path_outside_the_root(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "outside" / "verdict.json"
    assert runner.invoke(app, ["check", "--record", str(out)]).exit_code == EXIT_OK
    assert _read(out)["passed"] is True
    assert not (out.parent / "verdict.json.tmp").exists()


def test_record_accepts_a_path_inside_the_root_that_no_gate_reads(project: Path) -> None:
    out = project / "docs" / "verdict.json"
    assert runner.invoke(app, ["check", "--record", str(out)]).exit_code == EXIT_OK
    record = _read(out)
    assert record["passed"] is True
    measured = tree.measure(project, config_mod.load(project))
    assert (
        measured is not None and measured.tree == record["tree"]
    )  # the record moved nothing gated


def test_a_red_run_is_recorded_with_passed_false_and_exits_two(
    project: Path, tmp_path: Path
) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    out = tmp_path / "verdict.json"
    assert runner.invoke(app, ["check", "--record", str(out)]).exit_code == EXIT_GATE_FAILURE
    record = _read(out)
    assert record["passed"] is False
    assert [(line["gate"], line["passed"]) for line in record["verdict"]] == [
        ("size", False),
        ("complexity", True),
    ]
    assert record["verdict"][0]["diagnostics"] == 1


def test_a_lock_rejected_check_writes_no_record(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "verdict.json"
    with base.exclusive_run(project):
        result = runner.invoke(app, ["check", "--record", str(out)])
    assert result.exit_code == EXIT_OK
    assert "in progress" in _text(result)
    assert not out.exists()


def test_stop_check_has_no_record_option(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "verdict.json"
    result = runner.invoke(app, ["stop-check", "--record", str(out)], input=STOP_PAYLOAD)
    assert result.exit_code != EXIT_OK
    assert "No such option" in _text(result)
    assert not out.exists()
    assert _log(project) == []


def test_the_log_of_a_recorded_run_matches_an_unrecorded_run_line_for_line(
    project: Path, tmp_path: Path
) -> None:
    runner.invoke(app, ["check"])
    plain = _log(project)
    runner.invoke(app, ["check", "--record", str(tmp_path / "verdict.json")])
    recorded = _log(project)[len(plain) :]
    assert [line["kind"] for line in plain] == [
        "run.started",
        "gate.finished",
        "gate.finished",
        "run.finished",
    ]
    assert [_stable(line) for line in recorded] == [_stable(line) for line in plain]


# --- the digest ----------------------------------------------------------------


def test_the_verdict_digest_ignores_durations_timestamps_and_run_ids() -> None:
    lines = _lines_of([_result("size", {"worst_function_lines": 3}), _result("complexity", 2)])
    slower = [{**line, "duration": line["duration"] + 9.5} for line in lines]
    enveloped = [{**line, "at": "2026-09-15T00:00:00+00:00", "run": "r1", "v": 1} for line in lines]
    assert verdict.digest(slower) == verdict.digest(lines) == verdict.digest(enveloped)


def test_the_verdict_digest_moves_when_one_actual_changes() -> None:
    lines = _lines_of([_result("size", {"worst_function_lines": 3}), _result("complexity", 2)])
    changed = [dict(line) for line in lines]
    changed[1]["actual"] = 3
    assert verdict.digest(changed) != verdict.digest(lines)


def test_the_archived_baseline_run_digests_to_the_predicted_value() -> None:
    lines = events.read(ARCHIVE)
    assert len(lines) == 11
    assert {line["kind"] for line in lines} == {events.GATE_FINISHED}
    assert {line["run"] for line in lines} == {ARCHIVE_RUN}
    record = verdict.from_lines(lines, ARCHIVE_RUN)
    assert record.verdict_sha256 == ARCHIVE_DIGEST
    assert record.verdict == [_payload(line) for line in lines]
    assert record.passed is True


# --- verdict export ------------------------------------------------------------


def test_record_and_export_of_one_run_agree_in_every_field_but_harness(
    project: Path, tmp_path: Path
) -> None:
    live, exported = tmp_path / "live.json", tmp_path / "exported.json"
    runner.invoke(app, ["check", "--record", str(live)])
    (finished,) = _events(project, events.RUN_FINISHED)
    result = runner.invoke(app, ["verdict", "export", finished["run"], str(exported)])
    assert result.exit_code == EXIT_OK
    a, b = _read(live), _read(exported)
    assert a.pop("harness") == verdict.harness()
    assert b.pop("harness") is None
    assert a == b


def test_export_refuses_a_reused_run_and_names_the_run_it_deferred_to(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(app, ["check"])
    # One process, one second: give the skip its own run id, as a real hook has.
    monkeypatch.setattr(events, "new_run_id", lambda: "20260915T000000-2")
    runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    (reused,) = _events(project, events.RUN_REUSED)
    out = tmp_path / "verdict.json"
    result = runner.invoke(app, ["verdict", "export", reused["run"], str(out)])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert reused["reused_run"] in _text(result)
    assert not out.exists()


def test_export_of_an_unknown_run_exits_one(project: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["check"])
    out = tmp_path / "verdict.json"
    result = runner.invoke(app, ["verdict", "export", "19700101T000000-1", str(out)])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "no lines" in _text(result)
    assert not out.exists()


def test_export_of_a_run_without_boundaries_leaves_the_boundary_fields_null(
    project: Path, tmp_path: Path
) -> None:
    out = tmp_path / "verdict.json"
    result = runner.invoke(app, ["verdict", "export", ARCHIVE_RUN, str(out), "--log", str(ARCHIVE)])
    assert result.exit_code == EXIT_OK
    record = _read(out)
    assert {
        key: record[key] for key in ("command", "changed", "gates", "finished_at", "tree", "files")
    } == {
        "command": None,
        "changed": None,
        "gates": None,
        "finished_at": None,
        "tree": None,
        "files": None,
    }
    assert record["harness"] is None
    assert record["verdict_sha256"] == ARCHIVE_DIGEST
    assert len(record["verdict"]) == 11


def test_export_with_a_log_path_needs_no_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "gauntlet.toml").exists()
    out = tmp_path / "verdict.json"
    result = runner.invoke(app, ["verdict", "export", ARCHIVE_RUN, str(out), "--log", str(ARCHIVE)])
    assert result.exit_code == EXIT_OK
    assert _read(out)["run"] == ARCHIVE_RUN


def test_export_writes_no_event(project: Path, tmp_path: Path) -> None:
    runner.invoke(app, ["check"])
    (finished,) = _events(project, events.RUN_FINISHED)
    before = events.events_path(project).read_bytes()
    archive_before = ARCHIVE.read_bytes()
    runner.invoke(app, ["verdict", "export", finished["run"], str(tmp_path / "a.json")])
    runner.invoke(
        app, ["verdict", "export", ARCHIVE_RUN, str(tmp_path / "b.json"), "--log", str(ARCHIVE)]
    )
    assert events.events_path(project).read_bytes() == before
    assert ARCHIVE.read_bytes() == archive_before


# --- the harness -----------------------------------------------------------------


def _line(package: Path, rel: str) -> bytes:
    content = (package / rel).read_bytes()
    return hashlib.sha256(content).hexdigest().encode("ascii") + b"  " + rel.encode() + b"\n"


def test_harness_source_is_the_tree_hash_pipeline_over_the_package_files(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    (package / "sub").mkdir(parents=True)
    (package / "b.py").write_text("b = 2\n")
    (package / "a.py").write_text("a = 1\n")
    (package / "sub" / "c.py").write_text("c = 3\n")
    (package / "sub" / "__init__.py").write_text("")
    expected = hashlib.sha256(
        _line(package, "a.py")
        + _line(package, "b.py")
        + _line(package, "sub/__init__.py")
        + _line(package, "sub/c.py")
    ).hexdigest()
    assert verdict.harness(package) == {"version": __version__, "source": expected, "files": 4}
    assert verdict.harness()["version"] == "0.1.0"


def test_harness_source_skips_editor_lock_files_and_non_python_files(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "a.py").write_text("a = 1\n")
    clean = verdict.harness(package)
    (package / ".#a.py").symlink_to("nowhere")
    (package / "#a.py#").write_text("autosave\n")
    (package / "notes.txt").write_text("words\n")
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00")
    assert verdict.harness(package) == clean
    assert clean["files"] == 1
