"""Duplication gate: token-level clone detection via jscpd.

jscpd is language-agnostic, so this same gate serves the future C# adapter.
Duplication is a distinctive agent failure mode: an agent that cannot find the
existing helper writes a second one, and every individual edit looks fine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gauntlet.gates.base import Diagnostic, GateContext, GateResult, run_cmd, timed

name = "duplication"

DEFAULT_MIN_LINES = 5
DEFAULT_MIN_TOKENS = 50
INSTALL_HINT = "jscpd not found. Install it with `npm install -g jscpd` (requires Node)."


def _rel(path_str: str, root: Path) -> str:
    try:
        return str(Path(path_str).resolve().relative_to(root.resolve()))
    except ValueError:
        return path_str


def _diagnostic(duplicate: dict[str, Any], root: Path) -> Diagnostic:
    first = duplicate.get("firstFile", {})
    second = duplicate.get("secondFile", {})
    lines = int(duplicate.get("lines", 0))
    return Diagnostic(
        file=_rel(str(first.get("name", "?")), root),
        line=int(first.get("start", 0)) or None,
        value=lines,
        message=(
            f"{lines} duplicated lines, also at {_rel(str(second.get('name', '?')), root)}:"
            f"{second.get('start', '?')}. Extract the shared logic into one function "
            f"and call it from both places."
        ),
    )


def parse_jscpd(report: dict[str, Any], root: Path) -> tuple[int, list[Diagnostic]]:
    """jscpd JSON report -> (clone count, diagnostics), largest clone first."""
    duplicates = report.get("duplicates", [])
    ordered = sorted(duplicates, key=lambda d: -int(d.get("lines", 0)))
    return len(duplicates), [_diagnostic(d, root) for d in ordered]


def _command(ctx: GateContext, config: dict[str, Any], out_dir: Path) -> list[str]:
    return [
        "jscpd",
        *ctx.tool_targets(),
        "--reporters",
        "json",
        "--output",
        str(out_dir),
        "--min-lines",
        str(config.get("min_lines", DEFAULT_MIN_LINES)),
        "--min-tokens",
        str(config.get("min_tokens", DEFAULT_MIN_TOKENS)),
        "--silent",
    ]


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    limit = int(config.get("max_duplicate_blocks", 0))
    out_dir = ctx.project_root / ".gauntlet" / "jscpd"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        proc = run_cmd(_command(ctx, config, out_dir), cwd=ctx.project_root)
    except FileNotFoundError:
        return GateResult(gate=name, passed=False, threshold=limit, actual=None, error=INSTALL_HINT)

    report_path = out_dir / "jscpd-report.json"
    if not report_path.exists():
        return GateResult(
            gate=name,
            passed=False,
            threshold=limit,
            actual=None,
            error=f"jscpd produced no report: {(proc.stderr or proc.stdout).strip()[:500]}",
        )

    count, diagnostics = parse_jscpd(json.loads(report_path.read_text()), ctx.project_root)
    return GateResult(
        gate=name, passed=count <= limit, threshold=limit, actual=count, diagnostics=diagnostics
    )
