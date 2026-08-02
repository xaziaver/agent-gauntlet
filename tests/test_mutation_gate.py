from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet.adapters import python as python_adapter
from gauntlet.adapters.python import MutationRun
from gauntlet.gates import mutation
from gauntlet.gates.base import GateContext

SURVIVORS = ["m.x_f__mutmut_2"]
TOTAL = 4  # 3 killed, 1 survived


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
        python_adapter,
        "run_mutmut",
        lambda *a, **k: MutationRun(ok=True, total=TOTAL, survivors=SURVIVORS),
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
    assert "75.0%" in str(result.actual)  # 3 of 4 killed


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
        lambda *a, **k: MutationRun(ok=False, error="could not run 'mutmut'"),
    )
    result = mutation.run(_ctx(project), {"scope": "full"})
    assert result.passed is False
    assert "mutmut" in (result.error or "")


def test_killed_is_derived_from_the_run_total(project: Path, fake_mutmut: None) -> None:
    """`mutmut results` lists only unkilled mutants — counting its lines gave 0 killed."""
    result = mutation.run(_ctx(project), {"min_score": 0, "scope": "full"})
    assert "3 killed" in str(result.actual)


def test_a_copy_failure_is_explained(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mutmut's raw traceback tells an agent nothing actionable."""
    traceback = "FileNotFoundError: [Errno 2] No such file: 'src/gauntlet/.#cli.py'"
    monkeypatch.setattr(
        python_adapter, "run_mutmut", lambda *a, **k: MutationRun(ok=False, error=traceback)
    )
    result = mutation.run(_ctx(project), {"scope": "full"})
    assert "editor lock" in (result.error or "").lower()


def test_an_unrelated_error_is_passed_through_unchanged() -> None:
    assert mutation.explain("mutmut: no [tool.mutmut]") == "mutmut: no [tool.mutmut]"
