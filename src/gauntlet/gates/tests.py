"""Tests gate: the suite must pass. Also produces the coverage artifact in one run."""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from gauntlet import artifacts
from gauntlet.gates.base import (
    Diagnostic,
    GateContext,
    GateResult,
    interpreter_note,
    run_cmd,
    timed,
)

name = "tests"

TRACEBACK_TAIL_LINES = 25
COUNT_KEYS = ("tests", "failures", "errors", "skipped")
THRESHOLD = "all passing"
NO_TESTS_COLLECTED = 5
COVERAGE_CONSUMERS = frozenset({"coverage", "crap"})


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


def _headline(node: ET.Element) -> str:
    """The junit `message`: the one line a whole class of failures shares."""
    return (node.get("message") or node.get("type") or "test failed").strip()


def _case_diagnostic(case: ET.Element, node: ET.Element) -> Diagnostic:
    headline = _headline(node)
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


def _grouped(diagnostics: list[Diagnostic]) -> Diagnostic:
    """One headline's diagnostics as one: the first case's, carrying the count."""
    first = diagnostics[0]
    if len(diagnostics) == 1:
        return first
    prefix = f"{len(diagnostics)} test(s) failed the same way — first: "
    return dataclasses.replace(first, message=prefix + first.message)


def _collapsed(cases: list[ET.Element]) -> list[Diagnostic]:
    """Failed cases sharing a headline become one diagnostic, in first-occurrence order.

    One unbound step fails every scenario the same way; reported once per scenario,
    each with a traceback tail, the report outgrows the hook's output limit while
    saying one thing. A headline seen once yields the diagnostic it always did.
    """
    groups: dict[str, list[Diagnostic]] = {}
    for case in cases:
        node = _failure_node(case)
        if node is not None:
            groups.setdefault(_headline(node), []).append(_case_diagnostic(case, node))
    return [_grouped(diagnostics) for diagnostics in groups.values()]


def parse_junit(junit_path: Path) -> tuple[dict[str, int], list[Diagnostic]]:
    """junitxml file -> (counts, one diagnostic per distinct failure headline).

    The counts are the file's own; only the diagnostics collapse.
    """
    root = ET.parse(junit_path).getroot()
    return _counts(root), _collapsed(list(root.iter("testcase")))


def _pytest_command(ctx: GateContext, junit: Path) -> list[str]:
    cmd = [ctx.python, "-m", "pytest", str(ctx.tests), "-q", f"--junitxml={junit}"]
    if COVERAGE_CONSUMERS & set(ctx.enabled_gates):
        # One suite run, all artifacts — the coverage and crap gates read the JSON.
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


def _delete_last_run(root: Path) -> None:
    """The last run's junit.xml and coverage.json go before pytest starts.

    A collection error leaves coverage.json untouched, and the coverage and crap
    gates read whatever is on disk: deleting first makes a stale read impossible
    rather than detected.
    """
    for artifact in (artifacts.JUNIT_ARTIFACT, artifacts.COVERAGE_ARTIFACT):
        (root / artifact).unlink(missing_ok=True)


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:  # noqa: ARG001
    # `config` is unused but required by the Gate protocol's uniform signature.
    junit = ctx.project_root / artifacts.JUNIT_ARTIFACT
    junit.parent.mkdir(exist_ok=True)
    _delete_last_run(ctx.project_root)

    proc = run_cmd(_pytest_command(ctx, junit), cwd=ctx.project_root)
    if proc.returncode == NO_TESTS_COLLECTED:
        return _no_tests_result(ctx)
    if proc.returncode not in (0, 1) or not junit.exists():
        return GateResult(
            gate=name,
            passed=False,
            threshold=THRESHOLD,
            actual=None,
            error=f"pytest exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:800]}"
            + interpreter_note(ctx),
        )

    counts, diagnostics = parse_junit(junit)
    return _result(counts, diagnostics, proc.returncode)
