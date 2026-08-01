from __future__ import annotations

import sys
from pathlib import Path

from gauntlet import doctor

ALL_GATES = ["static", "complexity", "tests", "coverage", "crap", "duplication", "acceptance"]


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
