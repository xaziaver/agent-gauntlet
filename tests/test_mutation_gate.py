from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet.adapters import python as python_adapter
from gauntlet.adapters.base import RunResult
from gauntlet.gates import mutation
from gauntlet.gates.base import GateContext

RESULTS = """\
    m.x_f__mutmut_1: killed
    m.x_f__mutmut_2: survived
    m.x_g__mutmut_3: killed
    m.x_g__mutmut_4: killed
"""

DIFF = "--- m.py\n+++ m.py\n-    return a > b\n+    return a >= b\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def _ctx(root: Path, changed: list[Path] | None = None) -> GateContext:
    return GateContext(
        project_root=root, src=root / "src", tests=root / "tests", changed_files=changed
    )


@pytest.fixture
def fake_mutmut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        python_adapter, "run_mutmut", lambda *a, **k: RunResult(passed=True, output=RESULTS)
    )
    monkeypatch.setattr(
        python_adapter, "show_mutant", lambda *a, **k: ("return a > b", "return a >= b")
    )


@pytest.mark.parametrize(
    ("killed", "equivalent", "unresolved", "expected"),
    [(9, 0, 1, 90.0), (10, 0, 0, 100.0), (8, 2, 0, 100.0), (0, 0, 0, 100.0), (1, 0, 3, 25.0)],
)
def test_score_counts_reviewed_equivalents_as_killed(
    killed: int, equivalent: int, unresolved: int, expected: float
) -> None:
    assert mutation.score(killed, equivalent, unresolved) == expected


def test_a_surviving_mutant_below_the_threshold_fails(project: Path, fake_mutmut: None) -> None:
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    assert result.passed is False
    assert "75.0%" in str(result.actual)


def test_the_same_run_passes_under_a_lower_threshold(project: Path, fake_mutmut: None) -> None:
    result = mutation.run(_ctx(project), {"min_score": 70, "scope": "full"})
    assert result.passed is True


def test_require_review_fails_on_any_unresolved_survivor(project: Path, fake_mutmut: None) -> None:
    result = mutation.run(_ctx(project), {"min_score": 0, "scope": "full", "require_review": True})
    assert result.passed is False


def test_the_diagnostic_names_the_mutation_and_both_remedies(
    project: Path, fake_mutmut: None
) -> None:
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    message = result.diagnostics[0].message
    assert "return a > b" in message
    assert "Add a test that fails under it" in message
    assert "gauntlet mutant approve-code" in message


def test_changed_scope_with_nothing_changed_skips_the_run(project: Path) -> None:
    result = mutation.run(_ctx(project, changed=[]), {"scope": "changed"})
    assert result.passed is True
    assert result.actual == "no changed modules"


def test_a_mutmut_failure_is_an_error_not_a_pass(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        python_adapter,
        "run_mutmut",
        lambda *a, **k: RunResult(passed=False, output="could not run 'mutmut'"),
    )
    result = mutation.run(_ctx(project), {"scope": "full"})
    assert result.passed is False
    assert "mutmut" in (result.error or "")


def test_timeouts_count_as_killed() -> None:
    buckets = python_adapter.parse_results("    m.x_f__mutmut_1: timeout\n")
    assert mutation._killed_count(buckets) == 1
