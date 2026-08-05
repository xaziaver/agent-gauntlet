"""CLI tests: the exit-code contract every integration depends on."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import events
from gauntlet.cli import EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE, EXIT_OK, app
from gauntlet.gates import base

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

LONG_FUNCTION = "def big():\n" + "    x = 1\n" * 30

STOP_PAYLOAD = json.dumps({"hook_event_name": "Stop", "session_id": "s1"})


def _text(result: Any) -> str:
    """CliRunner output. Recent click merges stderr into .output; older versions don't."""
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
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_version_exits_zero() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == EXIT_OK
    assert "0.1" in result.output


def test_missing_config_exits_one_without_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "config error" in _text(result)


def test_unknown_gate_exits_one(project: Path) -> None:
    result = runner.invoke(app, ["check", "--gates", "nosuchgate"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "unknown gate" in _text(result)


def test_no_gates_enabled_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "gauntlet.toml").write_text(
        '[project]\nlanguage = "python"\nsrc = "src/"\ntests = "tests/"\n'
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "no gates enabled" in _text(result)


def test_clean_project_exits_zero(project: Path) -> None:
    (project / "src" / "a.py").write_text("def add(a, b):\n    return a + b\n")
    result = runner.invoke(app, ["check", "--gates", "size,complexity"])
    assert result.exit_code == EXIT_OK
    assert "GAUNTLET PASSED" in _text(result)


def test_violation_exits_two(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["check", "--gates", "size"])
    assert result.exit_code == EXIT_GATE_FAILURE
    assert "GAUNTLET FAILED" in _text(result)


def test_json_output_is_parsable(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["check", "--gates", "size", "--json"])
    payload = json.loads(_text(result))
    assert payload["passed"] is False
    assert payload["gates"][0]["gate"] == "size"


def test_fail_fast_skips_later_gates(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["check", "--gates", "size,complexity", "--fail-fast", "--json"])
    payload = json.loads(_text(result))
    assert result.exit_code == EXIT_GATE_FAILURE
    assert [g["gate"] for g in payload["gates"]] == ["size"]


def test_changed_flag_finds_untracked_files_in_a_git_repo(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["check", "--gates", "size", "--changed"])
    assert result.exit_code == EXIT_GATE_FAILURE


def test_changed_flag_outside_a_git_repo_analyzes_nothing(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["check", "--gates", "size", "--changed"])
    assert result.exit_code == EXIT_OK


def test_find_root_lets_check_run_from_a_subdirectory(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    monkeypatch.chdir(project / "src")
    result = runner.invoke(app, ["check", "--gates", "size"])
    assert result.exit_code == EXIT_GATE_FAILURE


def test_guard_allows_an_ordinary_edit(project: Path) -> None:
    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": str(project / "src" / "a.py")}}
    )
    result = runner.invoke(app, ["guard"], input=payload)
    assert result.exit_code == EXIT_OK


def test_guard_blocks_a_threshold_edit_with_exit_two(project: Path) -> None:
    payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": str(project / "gauntlet.toml")}}
    )
    result = runner.invoke(app, ["guard"], input=payload)
    assert result.exit_code == EXIT_GATE_FAILURE
    assert "protected Gauntlet file" in _text(result)


def test_guard_fails_open_on_a_malformed_payload(project: Path) -> None:
    """Exit 1 is non-blocking in Claude Code: a broken payload must not wedge the agent."""
    result = runner.invoke(app, ["guard"], input="not json")
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_guard_fails_open_without_a_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "gauntlet.toml"}})
    result = runner.invoke(app, ["guard"], input=payload)
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_lock_writes_the_registry(project: Path) -> None:
    result = runner.invoke(app, ["lock"])
    assert result.exit_code == EXIT_OK
    assert (project / "gauntlet.lock.json").exists()
    assert "approved  gauntlet.toml" in _text(result)


def test_verify_without_a_lock_file_passes_with_a_nudge(project: Path) -> None:
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == EXIT_OK
    assert "not locked" in _text(result)


def test_verify_passes_immediately_after_lock(project: Path) -> None:
    runner.invoke(app, ["lock"])
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == EXIT_OK


def test_verify_catches_a_threshold_weakened_outside_the_guard(project: Path) -> None:
    """The Bash-bypass case: the guard never fired, verification still catches it."""
    runner.invoke(app, ["lock"])
    (project / "gauntlet.toml").write_text(CONFIG.replace("max = 6", "max = 99"))
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == EXIT_GATE_FAILURE
    assert "changed since it was approved" in _text(result)


def test_verify_rejects_a_corrupt_lock_file(project: Path) -> None:
    (project / "gauntlet.lock.json").write_text("{not json")
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_protect_gate_runs_first_in_the_report(project: Path) -> None:
    (project / "gauntlet.toml").write_text(CONFIG + "\n[gates.protect]\n")
    result = runner.invoke(app, ["check", "--json"])
    payload = json.loads(_text(result))
    assert payload["gates"][0]["gate"] == "protect"


def test_stop_check_exits_zero_when_the_gates_pass(project: Path) -> None:
    (project / "src" / "a.py").write_text("def add(a, b):\n    return a + b\n")
    result = runner.invoke(app, ["stop-check"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_OK


def test_stop_check_bounces_the_agent_while_under_the_cap(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["stop-check", "--max-attempts", "3"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_GATE_FAILURE
    assert "GAUNTLET FAILED" in _text(result)


def test_stop_check_escalates_to_the_human_at_the_cap(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    for _ in range(2):
        runner.invoke(app, ["stop-check", "--max-attempts", "3"], input=STOP_PAYLOAD)
    result = runner.invoke(app, ["stop-check", "--max-attempts", "3"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_OK
    assert "systemMessage" in _text(result)
    assert "3 attempts" in _text(result)


def test_a_passing_run_resets_the_attempt_count(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    runner.invoke(app, ["stop-check", "--max-attempts", "2"], input=STOP_PAYLOAD)
    (project / "src" / "a.py").write_text("def add(a, b):\n    return a + b\n")
    runner.invoke(app, ["stop-check", "--max-attempts", "2"], input=STOP_PAYLOAD)
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["stop-check", "--max-attempts", "2"], input=STOP_PAYLOAD)
    assert result.exit_code == EXIT_GATE_FAILURE  # back to attempt 1, not escalating


def test_init_writes_claude_code_integration(project: Path) -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == EXIT_OK
    assert (project / ".claude" / "settings.json").exists()
    assert (project / "CLAUDE.md").exists()
    assert "gauntlet lock" in _text(result)


def test_init_is_idempotent(project: Path) -> None:
    runner.invoke(app, ["init"])
    first = (project / ".claude" / "settings.json").read_text()
    result = runner.invoke(app, ["init"])
    assert (project / ".claude" / "settings.json").read_text() == first
    assert "unchanged" in _text(result)


def test_init_dry_run_writes_nothing(project: Path) -> None:
    result = runner.invoke(app, ["init", "--dry-run"])
    assert result.exit_code == EXIT_OK
    assert not (project / ".claude").exists()
    assert "would write" in _text(result)


def test_init_generic_writes_ci_integration(project: Path) -> None:
    runner.invoke(app, ["init", "--agent", "generic"])
    assert (project / ".pre-commit-config.yaml").exists()
    assert (project / ".github" / "workflows" / "gauntlet.yml").exists()


def test_init_rejects_an_unknown_agent(project: Path) -> None:
    result = runner.invoke(app, ["init", "--agent", "nope"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_generated_settings_are_unapproved_until_locked(project: Path) -> None:
    """init must not self-approve: a human signs off on what it generated."""
    runner.invoke(app, ["lock"])
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["verify"])
    assert result.exit_code == EXIT_GATE_FAILURE
    assert "not approved" in _text(result)


def test_doctor_reports_and_exits_by_health(project: Path) -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code in (EXIT_OK, EXIT_CONFIG_ERROR)
    assert "needed by" in _text(result)


def test_init_bootstraps_a_project_from_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == EXIT_OK
    assert (tmp_path / "gauntlet.toml").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_check_records_a_run_in_the_event_log(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    runner.invoke(app, ["check", "--gates", "size"])
    kinds = [i["kind"] for i in events.read(events.events_path(project))]
    assert events.RUN_STARTED in kinds
    assert events.GATE_FINISHED in kinds
    assert events.RUN_FINISHED in kinds


def test_the_events_command_shows_recent_activity(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    runner.invoke(app, ["check", "--gates", "size"])
    result = runner.invoke(app, ["events", "--limit", "5"])
    assert result.exit_code == EXIT_OK
    assert "gate.finished" in _text(result)


def test_a_guard_block_is_recorded(project: Path) -> None:
    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": str(project / "gauntlet.toml")}}
    )
    runner.invoke(app, ["guard"], input=payload)
    kinds = [i["kind"] for i in events.read(events.events_path(project))]
    assert events.AGENT_BLOCKED in kinds


def test_status_always_exits_zero_even_when_gates_fail(project: Path) -> None:
    """A report, not a gate."""
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    result = runner.invoke(app, ["status", "--run"])
    assert result.exit_code == EXIT_OK
    assert "GATES     FAILING" in _text(result)


def test_status_json_is_parsable(project: Path) -> None:
    result = runner.invoke(app, ["status", "--json"])
    payload = json.loads(_text(result))
    assert "pending" in payload
    assert "gates" in payload


def test_a_concurrent_run_exits_zero_rather_than_interleaving(project: Path) -> None:
    """Two runs share coverage.json and junit.xml; interleaving reports failures
    that are not real, which is worse than no gate at all."""
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    with base.exclusive_run(project):
        result = runner.invoke(app, ["check", "--gates", "size"])
    assert result.exit_code == EXIT_OK
    assert "in progress" in _text(result)


def test_the_lock_is_released_after_a_run(project: Path) -> None:
    (project / "src" / "a.py").write_text(LONG_FUNCTION)
    runner.invoke(app, ["check", "--gates", "size"])
    result = runner.invoke(app, ["check", "--gates", "size"])
    assert result.exit_code == EXIT_GATE_FAILURE
