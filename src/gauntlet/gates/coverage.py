"""Coverage gate: reads the artifact produced by the tests gate. Runs no subprocess."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gauntlet import artifacts
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "coverage"

MISSING_LINES_SHOWN = 10


class _ArtifactError(Exception):
    """The coverage artifact is missing or unreadable."""


def _load_artifact(root: Path) -> dict[str, Any]:
    path = root / ".gauntlet" / "coverage.json"
    if not path.exists():
        raise _ArtifactError(
            "No .gauntlet/coverage.json — the tests gate must run before the "
            "coverage gate (check gate order / --gates selection)."
        )
    try:
        parsed: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise _ArtifactError(f"coverage.json unreadable: {exc}") from exc
    return parsed


def _branch_percent(totals: dict[str, Any]) -> float | None:
    total = int(totals.get("num_branches", 0))
    if not total:
        return None
    covered = int(totals.get("covered_branches", 0))
    return round(100.0 * covered / total, 2)


def _percent(item: tuple[str, dict[str, Any]]) -> float:
    return float(item[1].get("summary", {}).get("percent_covered", 100.0))


def _file_diagnostic(path: str, info: dict[str, Any], line_min: float) -> Diagnostic | None:
    pct = round(float(info.get("summary", {}).get("percent_covered", 100.0)), 2)
    if pct >= line_min:
        return None
    missing = info.get("missing_lines", [])
    shown = ", ".join(str(n) for n in missing[:MISSING_LINES_SHOWN])
    extra = len(missing) - MISSING_LINES_SHOWN
    more = f" (+{extra} more)" if extra > 0 else ""
    return Diagnostic(
        file=path,
        value=pct,
        message=(
            f"{path} is {pct}% covered (min {line_min}%). Add tests that exercise "
            f"lines: {shown}{more}."
        ),
    )


def _file_diagnostics(files: dict[str, Any], file_min: float | None) -> list[Diagnostic]:
    if file_min is None:
        return []
    candidates = (
        _file_diagnostic(path, info, file_min) for path, info in sorted(files.items(), key=_percent)
    )
    return [d for d in candidates if d is not None]


def _branch_ok(branch_pct: float | None, branch_min: float | None) -> bool:
    if branch_min is None or branch_pct is None:
        return True
    return branch_pct >= branch_min


def judge(
    data: dict[str, Any], line_min: float, branch_min: float | None, file_min: float | None = None
) -> tuple[bool, dict[str, Any], list[Diagnostic]]:
    """coverage.json -> (passed, actual summary, per-file diagnostics).

    Every diagnostic corresponds to a rule that is actually enforced: with
    per_file_min unset the gate judges the aggregate only and stays silent about
    individual files, so a passing gate never emits guidance an agent might
    mistake for a failure.
    """
    totals = data.get("totals", {})
    line_pct = round(float(totals.get("percent_covered", 0.0)), 2)
    branch_pct = _branch_percent(totals)
    actual: dict[str, Any] = {"line": line_pct}
    if branch_pct is not None:
        actual["branch"] = branch_pct

    diagnostics = _file_diagnostics(data.get("files", {}), file_min)
    passed = line_pct >= line_min and _branch_ok(branch_pct, branch_min) and not diagnostics
    return passed, actual, diagnostics


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    line_min = float(config.get("line", 90))
    branch_min = float(config["branch"]) if "branch" in config else None
    file_min = float(config["per_file_min"]) if "per_file_min" in config else None
    threshold = {"line": line_min, "branch": branch_min, "per_file": file_min}

    try:
        data = artifacts.load_coverage(ctx.project_root)
    except artifacts.ArtifactError as exc:
        return GateResult(gate=name, passed=False, threshold=threshold, actual=None, error=str(exc))

    passed, actual, diagnostics = judge(data, line_min, branch_min, file_min)
    return GateResult(
        gate=name, passed=passed, threshold=threshold, actual=actual, diagnostics=diagnostics
    )
