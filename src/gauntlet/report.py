"""Renders a list of GateResults as human text or machine-readable JSON."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any

from gauntlet.gates.base import Diagnostic, GateResult

PASS, FAIL = "\u2713", "\u2717"


def passed(results: list[GateResult]) -> bool:
    return all(r.passed for r in results)


def to_json(results: list[GateResult], max_diags: int = 10) -> str:
    """Stable, flat JSON. Keep it boring: agents parse this."""
    gates: list[dict[str, Any]] = []
    for result in results:
        payload = result.to_dict()
        diagnostics = payload["diagnostics"]
        payload["diagnostics_truncated"] = max(0, len(diagnostics) - max_diags)
        payload["diagnostics"] = diagnostics[:max_diags]
        gates.append(payload)
    return json.dumps({"passed": passed(results), "gates": gates}, indent=2)


def _actual(result: GateResult) -> str:
    """Gates whose `actual` is already a phrase: protect, static, tests."""
    return str(result.actual)


def _ceiling(result: GateResult, label: str) -> str:
    return f"worst {label} {result.actual} (max {result.threshold})"


def _size(result: GateResult) -> str:
    return (
        f"worst function {result.actual['worst_function_lines']} lines "
        f"(max {result.threshold['max_function_lines']})"
    )


def _metric(name: str, percent: float, minimum: float | None) -> str:
    return f"{name} {percent}%" + ("" if minimum is None else f" (min {minimum})")


def _coverage(result: GateResult) -> str:
    """`actual` carries whichever of line/branch coverage was measured."""
    minimums = result.threshold
    return ", ".join(
        _metric(name, percent, minimums.get(name)) for name, percent in result.actual.items()
    )


def _duplication(result: GateResult) -> str:
    blocks = "block" if result.actual == 1 else "blocks"
    return f"{result.actual} duplicate {blocks} (max {result.threshold})"


_SUMMARIES: dict[str, Callable[[GateResult], str]] = {
    "protect": _actual,
    "static": _actual,
    "tests": _actual,
    "size": _size,
    "complexity": functools.partial(_ceiling, label="complexity"),
    "crap": functools.partial(_ceiling, label="CRAP"),
    "coverage": _coverage,
    "duplication": _duplication,
}


def summary_line(result: GateResult) -> str:
    """One line per gate, with the reading phrased in that gate's own units.

    Every gate reports `threshold` and `actual` in a different shape — a count, a
    ceiling, a dict of percentages — so a generic `threshold=X actual=Y` renders as
    noise. An unrecognised gate falls back to printing `actual` verbatim.
    """
    mark = PASS if result.passed else FAIL
    if result.error:
        detail = f"ERROR: {result.error.strip().splitlines()[0]}"
    elif result.actual is None:
        detail = "no result"
    else:
        detail = _SUMMARIES.get(result.gate, _actual)(result)
    return f"{mark} {result.gate:<12} {detail}"


def _render_diagnostic(diagnostic: Diagnostic) -> str:
    location = diagnostic.file + (f":{diagnostic.line}" if diagnostic.line else "")
    return f"    {location}  {diagnostic.message}"


def _render_result(result: GateResult, max_diags: int) -> list[str]:
    mark = PASS if result.passed else FAIL
    header = (
        f"{mark} {result.gate:<12} threshold={result.threshold} "
        f"actual={result.actual} ({result.duration}s)"
    )
    lines = [header]
    if result.error:
        lines.append(f"    ERROR: {result.error}")
    lines.extend(_render_diagnostic(d) for d in result.diagnostics[:max_diags])
    hidden = len(result.diagnostics) - max_diags
    if hidden > 0:
        lines.append(f"    ... {hidden} more (raise [output].max_diagnostics_per_gate)")
    return lines


def to_human(results: list[GateResult], max_diags: int = 10) -> str:
    lines: list[str] = []
    for result in results:
        lines.extend(_render_result(result, max_diags))
    verdict = "GAUNTLET PASSED" if passed(results) else "GAUNTLET FAILED"
    return "\n".join([*lines, "", verdict])
