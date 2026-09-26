from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gauntlet.adapters import python as adapter


def test_passing_suite(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    assert adapter.run_acceptance(tmp_path, steps, sys.executable).passed is True


def test_failing_suite_carries_output(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    result = adapter.run_acceptance(tmp_path, steps, sys.executable)
    assert result.passed is False
    assert "test_bad" in result.output


def test_collecting_nothing_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    steps.mkdir()
    assert adapter.run_acceptance(tmp_path, steps, sys.executable).passed is False


def test_run_acceptance_accepts_several_targets(tmp_path: Path) -> None:
    """Only the named modules run, and a collection failure names them all."""
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "test_a.py").write_text("def test_a():\n    assert True\n")
    (steps / "test_b.py").write_text("def test_b():\n    assert True\n")
    (steps / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    (steps / "empty.py").write_text("")
    chosen = [steps / "test_a.py", steps / "test_b.py"]
    assert adapter.run_acceptance(tmp_path, chosen, sys.executable).passed is True
    assert adapter.run_acceptance(tmp_path, steps, sys.executable).passed is False
    empty = adapter.run_acceptance(
        tmp_path, [steps / "empty.py", steps / "empty.py"], sys.executable
    )
    assert empty.passed is False
    assert empty.output == f"no scenarios collected from {steps / 'empty.py'}, {steps / 'empty.py'}"


def test_interpreter_prefers_an_explicit_configuration(tmp_path: Path) -> None:
    assert adapter.interpreter(tmp_path, "/usr/bin/python3") == "/usr/bin/python3"


def test_interpreter_resolves_a_relative_configuration_against_the_root(tmp_path: Path) -> None:
    assert adapter.interpreter(tmp_path, "env/bin/python") == str(
        tmp_path / "env" / "bin" / "python"
    )


def test_interpreter_finds_a_local_venv_without_resolving_the_symlink(tmp_path: Path) -> None:
    """Resolving a venv's python yields the base interpreter, which loses site-packages."""
    base = tmp_path / "base" / "bin"
    base.mkdir(parents=True)
    real = base / "python3.12"
    real.write_text("#!/bin/sh\n")
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(real)

    assert adapter.interpreter(tmp_path) == str(venv_bin / "python")


def test_interpreter_uses_an_active_virtualenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv_bin = tmp_path / "env" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").write_text("#!/bin/sh\n")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "env"))
    assert adapter.interpreter(tmp_path) == str(venv_bin / "python")


def test_resolve_reports_a_fallback_only_when_nothing_else_matched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each earlier step of the order is not a fallback; only landing on us is."""
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    assert adapter.resolve(tmp_path) == adapter.Resolved(sys.executable, True)
    env_bin = tmp_path / "env" / "bin"
    env_bin.mkdir(parents=True)
    (env_bin / "python").write_text("")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "env"))
    assert adapter.resolve(tmp_path) == adapter.Resolved(str(env_bin / "python"), False)
    local_bin = tmp_path / ".venv" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "python").write_text("")
    assert adapter.resolve(tmp_path) == adapter.Resolved(str(local_bin / "python"), False)
    assert adapter.resolve(tmp_path, "/usr/bin/python3") == adapter.Resolved(
        "/usr/bin/python3", False
    )


def test_a_configured_interpreter_that_does_not_exist_is_not_a_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The human chose the path; the error will name it, which is the right message."""
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    resolved = adapter.resolve(tmp_path, "nowhere/python")
    assert resolved == adapter.Resolved(str(tmp_path / "nowhere" / "python"), False)
    assert not Path(resolved.python).exists()


def test_a_local_venv_beats_an_active_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local = tmp_path / ".venv" / "bin"
    local.mkdir(parents=True)
    (local / "python").write_text("#!/bin/sh\n")
    other = tmp_path / "other" / "bin"
    other.mkdir(parents=True)
    (other / "python").write_text("#!/bin/sh\n")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "other"))
    assert adapter.interpreter(tmp_path) == str(local / "python")
