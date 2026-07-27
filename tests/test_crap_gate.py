from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet.gates.crap import (
    FunctionCrap,
    crap_score,
    crap_scores,
    judge,
    normalize,
    required_coverage,
    span_coverage,
)


@pytest.mark.parametrize(
    ("complexity", "coverage", "expected"),
    [
        (6, 1.0, 6.0),  # fully covered: CRAP collapses to CC
        (6, 0.0, 42.0),  # untested: CC**2 + CC
        (1, 0.0, 2.0),  # trivial and untested is still cheap
        (10, 0.5, 22.5),  # 100 * 0.125 + 10
    ],
)
def test_formula(complexity: int, coverage: float, expected: float) -> None:
    assert crap_score(complexity, coverage) == expected


def test_a_complex_function_in_a_covered_file_is_the_case_this_gate_exists_for() -> None:
    """CC 6 passes the complexity gate; 0% coverage of it can hide in a 95% covered file."""
    assert crap_score(6, 0.0) > 15


def test_required_coverage_is_reachable_below_the_ceiling() -> None:
    needed = required_coverage(6, 15.0)
    assert needed is not None
    assert 0.36 < needed < 0.38
    assert crap_score(6, needed + 0.01) <= 15


def test_required_coverage_is_total_when_complexity_equals_the_ceiling() -> None:
    assert required_coverage(15, 15.0) == pytest.approx(1.0)


def test_required_coverage_is_none_when_tests_cannot_help() -> None:
    assert required_coverage(20, 15.0) is None


def test_span_coverage_counts_statements_not_physical_lines() -> None:
    block = {"lineno": 10, "endline": 20}  # 11 physical lines, 4 statements
    assert span_coverage(block, executed={10, 11}, missing={12, 13}) == 0.5


def test_span_coverage_of_a_statementless_span_is_full() -> None:
    assert span_coverage({"lineno": 1, "endline": 3}, executed=set(), missing=set()) == 1.0


def test_span_coverage_ignores_lines_outside_the_function() -> None:
    block = {"lineno": 10, "endline": 12}
    assert span_coverage(block, executed={1, 2, 10, 11, 12}, missing={99}) == 1.0


def test_normalize_reconciles_absolute_and_relative_paths(tmp_path: Path) -> None:
    absolute = str(tmp_path / "src" / "a.py")
    assert normalize(absolute, tmp_path) == normalize("src/a.py", tmp_path) == "src/a.py"


def _blocks(**over: object) -> dict[str, list[dict[str, object]]]:
    block = {"name": "f", "lineno": 1, "endline": 4, "complexity": 6, "type": "function"}
    block.update(over)
    return {"/abs/src/a.py": [block]}


def test_join_matches_radon_and_coverage_paths(tmp_path: Path) -> None:
    cc = {
        str(tmp_path / "src" / "a.py"): [
            {"name": "f", "lineno": 1, "endline": 4, "complexity": 6, "type": "function"}
        ]
    }
    files = {"src/a.py": {"executed_lines": [], "missing_lines": [1, 2, 3, 4]}}
    scores = crap_scores(cc, files, tmp_path)
    assert len(scores) == 1
    assert scores[0].file == "src/a.py"
    assert scores[0].coverage == 0.0
    assert scores[0].score == 42.0


def test_class_blocks_are_excluded_to_avoid_double_counting(tmp_path: Path) -> None:
    cc = {
        "src/a.py": [
            {"name": "K", "lineno": 1, "endline": 9, "complexity": 12, "type": "class"},
            {
                "name": "m",
                "classname": "K",
                "lineno": 2,
                "endline": 4,
                "complexity": 6,
                "type": "method",
            },
        ]
    }
    files = {"src/a.py": {"executed_lines": [2, 3, 4], "missing_lines": []}}
    scores = crap_scores(cc, files, tmp_path)
    assert [s.symbol for s in scores] == ["K.m"]


def test_files_without_coverage_data_are_skipped_not_scored_as_zero(tmp_path: Path) -> None:
    """A path-normalization slip must surface as a bug, not fail the whole codebase."""
    assert crap_scores(_blocks(), {"src/other.py": {}}, tmp_path) == []


def test_radon_parse_errors_are_skipped(tmp_path: Path) -> None:
    cc = {"src/a.py": {"error": "invalid syntax"}}
    assert crap_scores(cc, {"src/a.py": {}}, tmp_path) == []


def _score(score: float, complexity: int = 6, coverage: float = 0.0) -> FunctionCrap:
    return FunctionCrap(
        file="src/a.py",
        symbol="f",
        line=1,
        complexity=complexity,
        coverage=coverage,
        score=score,
    )


def test_judge_passes_when_everything_is_under_the_ceiling() -> None:
    worst, diagnostics = judge([_score(10.0), _score(15.0)], ceiling=15.0)
    assert worst == 15.0
    assert diagnostics == []


def test_judge_orders_diagnostics_worst_first() -> None:
    _, diagnostics = judge([_score(20.0), _score(42.0)], ceiling=15.0)
    assert [d.value for d in diagnostics] == [42.0, 20.0]


def test_diagnostic_offers_the_coverage_remedy_when_it_is_available() -> None:
    _, diagnostics = judge([_score(42.0, complexity=6)], ceiling=15.0)
    assert "cover it to at least 37%" in diagnostics[0].message.lower()


def test_diagnostic_says_tests_cannot_help_when_complexity_alone_breaches() -> None:
    _, diagnostics = judge([_score(400.0, complexity=20)], ceiling=15.0)
    assert "tests alone cannot fix this" in diagnostics[0].message


def test_empty_input_is_clean() -> None:
    assert judge([], ceiling=15.0) == (0.0, [])
