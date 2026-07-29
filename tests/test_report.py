import json

from gauntlet import report
from gauntlet.gates.base import Diagnostic, GateResult


def _result(passed: bool = True, diagnostics: list[Diagnostic] | None = None) -> GateResult:
    return GateResult(
        gate="complexity",
        passed=passed,
        threshold=6,
        actual=9,
        diagnostics=diagnostics or [],
        duration=0.5,
    )


def _diags(n: int) -> list[Diagnostic]:
    return [Diagnostic(file=f"src/f{i}.py", line=i, message=f"too complex {i}") for i in range(n)]


def test_passed_requires_every_gate() -> None:
    assert report.passed([_result(True), _result(True)]) is True
    assert report.passed([_result(True), _result(False)]) is False


def test_human_report_marks_failure_and_verdict() -> None:
    text = report.to_human([_result(passed=False, diagnostics=_diags(1))])
    assert report.FAIL in text
    assert "GAUNTLET FAILED" in text
    assert "src/f0.py:0" in text or "src/f0.py" in text


def test_human_report_truncates_to_the_budget() -> None:
    text = report.to_human([_result(passed=False, diagnostics=_diags(15))], max_diags=10)
    assert "src/f9.py" in text
    assert "src/f10.py" not in text
    assert "... 5 more" in text


def test_json_report_states_how_many_were_hidden() -> None:
    payload = json.loads(report.to_json([_result(passed=False, diagnostics=_diags(15))], 10))
    gate = payload["gates"][0]
    assert payload["passed"] is False
    assert len(gate["diagnostics"]) == 10
    assert gate["diagnostics_truncated"] == 5


def test_json_report_is_untruncated_when_under_budget() -> None:
    payload = json.loads(report.to_json([_result(passed=False, diagnostics=_diags(2))], 10))
    assert payload["gates"][0]["diagnostics_truncated"] == 0


def test_error_is_surfaced_in_the_human_report() -> None:
    failed = GateResult(gate="tests", passed=False, threshold="x", actual=None, error="boom")
    assert "ERROR: boom" in report.to_human([failed])


def _gate(gate: str, threshold: object, actual: object, passed: bool = False) -> GateResult:
    return GateResult(gate=gate, passed=passed, threshold=threshold, actual=actual)


def test_summary_reads_ceiling_gates_in_their_own_units() -> None:
    assert report.summary_line(_gate("complexity", 6, 9)).endswith("worst complexity 9 (max 6)")
    assert report.summary_line(_gate("crap", 15, 21.5)).endswith("worst CRAP 21.5 (max 15)")


def test_summary_reads_the_function_ceiling_out_of_the_size_dicts() -> None:
    result = _gate(
        "size",
        {"max_function_lines": 25, "max_module_lines": 300},
        {"worst_function_lines": 31},
    )
    assert report.summary_line(result).endswith("worst function 31 lines (max 25)")


def test_summary_pairs_every_coverage_metric_with_its_minimum() -> None:
    result = _gate(
        "coverage",
        {"line": 95.0, "branch": 90.0, "per_file": 80.0},
        {"line": 92.5, "branch": 88.0},
    )
    assert report.summary_line(result).endswith("line 92.5% (min 95.0), branch 88.0% (min 90.0)")


def test_summary_omits_a_coverage_minimum_that_is_unset() -> None:
    result = _gate("coverage", {"line": 95.0, "branch": None}, {"line": 96.0, "branch": 88.0})
    assert report.summary_line(result).endswith("line 96.0% (min 95.0), branch 88.0%")


def test_summary_counts_duplicate_blocks_and_agrees_with_itself() -> None:
    assert report.summary_line(_gate("duplication", 0, 1)).endswith("1 duplicate block (max 0)")
    assert report.summary_line(_gate("duplication", 0, 3)).endswith("3 duplicate blocks (max 0)")


def test_summary_passes_through_gates_that_already_phrase_their_actual() -> None:
    assert report.summary_line(_gate("tests", "all passing", "12/14 passing")).endswith(
        "12/14 passing"
    )
    assert report.summary_line(_gate("static", "clean", "3 findings")).endswith("3 findings")
    assert report.summary_line(_gate("protect", "approved", "4/4 paths unchanged")).endswith(
        "4/4 paths unchanged"
    )


def test_summary_marks_pass_and_failure() -> None:
    assert report.summary_line(_gate("complexity", 6, 4, passed=True)).startswith(report.PASS)
    assert report.summary_line(_gate("complexity", 6, 9)).startswith(report.FAIL)


def test_summary_names_the_gate() -> None:
    assert "duplication" in report.summary_line(_gate("duplication", 0, 0, passed=True))


def test_summary_collapses_a_multiline_error_to_one_line() -> None:
    result = GateResult(
        gate="tests", passed=False, threshold="x", actual=None, error="pytest exited 2\ntraceback"
    )
    assert report.summary_line(result).endswith("ERROR: pytest exited 2")


def test_summary_reports_a_missing_actual_rather_than_none() -> None:
    assert report.summary_line(_gate("complexity", 6, None)).endswith("no result")


def test_summary_falls_back_to_actual_for_an_unknown_gate() -> None:
    assert report.summary_line(_gate("mutation", 80, "61% killed")).endswith("61% killed")
