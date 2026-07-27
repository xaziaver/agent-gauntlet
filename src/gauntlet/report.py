"""Renders a list of GateResults as human text or machine-readable JSON."""
from __future__ import annotations

import json
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


def _render_diagnostic(diagnostic: Diagnostic) -> str:
    location = diagnostic.file + (f":{diagnostic.line}" if diagnostic.line else "")
    return f"    {location}  {diagnostic.message}"


def _render_result(result: GateResult, max_diags: int) -> list[str]:
    mark = PASS if result.passed else FAIL
    lines = [
        f"{mark} {result.gate:<12} threshold={result.threshold} "
        f"actual={result.actual} ({result.duration}s)"
    ]
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
