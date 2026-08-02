from __future__ import annotations

import sys
from pathlib import Path

from gauntlet import doctor

ALL_GATES = [
    "static",
    "complexity",
    "tests",
    "coverage",
    "crap",
    "duplication",
    "mutation",
    "acceptance",
]


def _project(tmp_path: Path, pyproject: str = "") -> Path:
    (tmp_path / "mutants").mkdir()
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(pyproject)
    return tmp_path


def test_no_warning_when_the_mutation_gate_is_off(tmp_path: Path) -> None:
    assert doctor.warnings_for(_project(tmp_path), tmp_path / "src", ["tests"]) == []


def test_no_warning_without_a_mutants_directory(tmp_path: Path) -> None:
    assert doctor.warnings_for(tmp_path, tmp_path / "src", ["mutation"]) == []


def test_a_mutants_directory_without_the_pytest_ignore_warns(tmp_path: Path) -> None:
    """Otherwise a bare `pytest` fails with an opaque import-file-mismatch error."""
    warnings = doctor.warnings_for(_project(tmp_path), tmp_path / "src", ["mutation"])
    assert len(warnings) == 1
    assert "--ignore=mutants" in warnings[0]


def test_the_configured_ignore_silences_the_warning(tmp_path: Path) -> None:
    pyproject = '[tool.pytest.ini_options]\naddopts = "--ignore=mutants"\n'
    assert doctor.warnings_for(_project(tmp_path, pyproject), tmp_path / "src", ["mutation"]) == []


def test_render_shows_warnings(tmp_path: Path) -> None:
    text = doctor.render(doctor.run_checks(["static"]), None, ["something is off"])
    assert "WARNING  something is off" in text


def test_warnings_do_not_make_the_environment_unhealthy() -> None:
    """A warning is advisory: the gates pass pytest an explicit path and are unaffected."""
    assert doctor.healthy(doctor.run_checks(["static"])) is True


def test_checks_cover_only_the_enabled_gates() -> None:
    tools = [c.tool for c in doctor.run_checks(["size"])]
    assert tools == ["git"]  # only the --changed dependency remains


def test_all_tools_checked_for_a_full_config() -> None:
    tools = [c.tool for c in doctor.run_checks(ALL_GATES)]
    assert tools == list(doctor.CHECK_ORDER)


def test_a_module_missing_from_the_project_interpreter_is_reported(tmp_path: Path) -> None:
    fake = tmp_path / "python"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    checks = doctor.run_checks(["tests"], str(fake))
    pytest_check = next(c for c in checks if c.tool == "pytest")
    assert pytest_check.ok is False
    assert "not importable" in pytest_check.detail


def test_project_modules_are_checked_against_the_project_interpreter(tmp_path: Path) -> None:
    """pytest lives in the project's venv, not Gauntlet's — that is the whole point."""
    checks = doctor.run_checks(["tests"], sys.executable)
    assert next(c for c in checks if c.tool == "pytest").ok is True


def test_render_names_both_interpreters() -> None:
    text = doctor.render(doctor.run_checks(["static"]), "/proj/.venv/bin/python")
    assert "project python:  /proj/.venv/bin/python" in text


def test_editor_lock_files_are_warned_about(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / ".#module.py").symlink_to(src / "gone.py")
    warnings = doctor.warnings_for(tmp_path, src, ["mutation"])
    assert any("Editor lock" in w for w in warnings)


def test_a_clean_source_tree_produces_no_artifact_warning(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "module.py").write_text("x = 1\n")
    assert doctor.warnings_for(tmp_path, src, ["mutation"]) == []


def test_artifacts_are_ignored_when_the_mutation_gate_is_off(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / ".#module.py").symlink_to(src / "gone.py")
    assert doctor.warnings_for(tmp_path, src, ["tests"]) == []
