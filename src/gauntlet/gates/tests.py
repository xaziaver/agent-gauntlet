"""Tests gate: the suite must pass. Also produces the coverage artifact in one run."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from gauntlet.gates.base import Diagnostic, GateContext, GateResult, run_cmd, timed

name = "tests"

TRACEBACK_TAIL_LINES = 25
COUNT_KEYS = ("tests", "failures", "errors", "skipped")
THRESHOLD = "all passing"
NO_TESTS_COLLECTED = 5


def _failure_node(case: ET.Element) -> ET.Element | None:
    """The <failure> or <error> child of a testcase, if any.

    Written longhand on purpose: an Element with no children is falsy, so
    `case.find("failure") or case.find("error")` is subtly wrong.
    """
    for tag in ("failure", "error"):
        node = case.find(tag)
        if node is not None:
            return node
    return None


def _counts(root: ET.Element) -> dict[str, int]:
    """Element.iter() includes the root, so both <testsuites> and <testsuite> work."""
    counts = dict.fromkeys(COUNT_KEYS, 0)
    for suite in root.iter("testsuite"):
        for key in COUNT_KEYS:
            counts[key] += int(suite.get(key, 0))
    return counts


def _case_diagnostic(case: ET.Element) -> Diagnostic | None:
    node = _failure_node(case)
    if node is None:
        return None
    headline = (node.get("message") or node.get("type") or "test failed").strip()
    tail = "\n".join((node.text or "").splitlines()[-TRACEBACK_TAIL_LINES:]).strip()
    test_id = f"{case.get('classname', '')}.{case.get('name', '?')}".lstrip(".")
    return Diagnostic(
        file=case.get("file", "?"),
        line=int(case.get("line", 0)) or None,
        symbol=test_id,
        message=(
            f"{test_id} failed: {headline}\n"
            f"        Fix the code under test (or the test, if it encodes the wrong "
            f"expectation).\n{tail}"
        ),
    )


def parse_junit(junit_path: Path) -> tuple[dict[str, int], list[Diagnostic]]:
    """junitxml file -> (counts, one diagnostic per failed test)."""
    root = ET.parse(junit_path).getroot()
    diagnostics = [d for d in map(_case_diagnostic, root.iter("testcase")) if d is not None]
    return _counts(root), diagnostics


def _pytest_command(ctx: GateContext, junit: Path) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", str(ctx.tests), "-q", f"--junitxml={junit}"]
    if "coverage" in ctx.enabled_gates:
        # One suite run, two artifacts — the coverage gate reads the JSON, it never
        # re-runs pytest itself.
        cmd += [
            f"--cov={ctx.src}",
            "--cov-branch",
            f"--cov-report=json:{junit.parent / 'coverage.json'}",
        ]
    return cmd


def _no_tests_result(ctx: GateContext) -> GateResult:
    return GateResult(
        gate=name,
        passed=False,
        threshold=THRESHOLD,
        actual="no tests collected",
        diagnostics=[
            Diagnostic(
                file=str(ctx.tests),
                message=(
                    f"No tests were collected from {ctx.tests}. Write tests before declaring "
                    f"work complete; an empty suite is not a passing suite."
                ),
            )
        ],
    )


def _result(counts: dict[str, int], diagnostics: list[Diagnostic], returncode: int) -> GateResult:
    failed = counts["failures"] + counts["errors"]
    return GateResult(
        gate=name,
        passed=failed == 0 and returncode == 0,
        threshold=THRESHOLD,
        actual=f"{counts['tests'] - failed}/{counts['tests']} passing",
        diagnostics=diagnostics,
    )


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    artifacts = ctx.project_root / ".gauntlet"
    artifacts.mkdir(exist_ok=True)
    junit = artifacts / "junit.xml"

    proc = run_cmd(_pytest_command(ctx, junit), cwd=ctx.project_root)
    if proc.returncode == NO_TESTS_COLLECTED:
        return _no_tests_result(ctx)
    if proc.returncode not in (0, 1) or not junit.exists():
        return GateResult(
            gate=name,
            passed=False,
            threshold=THRESHOLD,
            actual=None,
            error=f"pytest exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:800]}",
        )

    counts, diagnostics = parse_junit(junit)
    return _result(counts, diagnostics, proc.returncode)
