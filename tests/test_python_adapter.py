from __future__ import annotations

from pathlib import Path

from gauntlet.adapters import python as adapter


def test_passing_suite(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    assert adapter.run_acceptance(tmp_path, steps).passed is True


def test_failing_suite_carries_output(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    result = adapter.run_acceptance(tmp_path, steps)
    assert result.passed is False
    assert "test_bad" in result.output


def test_collecting_nothing_is_a_failure_not_a_pass(tmp_path: Path) -> None:
    steps = tmp_path / "steps"
    steps.mkdir()
    assert adapter.run_acceptance(tmp_path, steps).passed is False
