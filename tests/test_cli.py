"""CLI tests: the exit-code contract every integration depends on."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet.cli import EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE, EXIT_OK, app

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
