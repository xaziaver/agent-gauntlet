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
