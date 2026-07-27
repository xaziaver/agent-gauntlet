from __future__ import annotations

import json
import sys
from typing import Any

from gauntlet.gates.base import Diagnostic, GateContext, GateResult, run_cmd, timed

name = "static"


def _ruff_diagnostic(item: dict[str, Any]) -> Diagnostic:
    hint = " (auto-fixable: run `ruff check --fix`)" if item.get("fix") else ""
    return Diagnostic(
        file=item["filename"],
        line=item["location"]["row"],
        symbol=item["code"],
        message=f"[ruff {item['code']}] {item['message']}{hint}",
    )


def parse_ruff(payload: str) -> list[Diagnostic]:
    return [_ruff_diagnostic(item) for item in json.loads(payload or "[]")]


def _json_object(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped.startswith("{"):
        return None
    parsed: dict[str, Any] = json.loads(stripped)
    return parsed


def parse_mypy(payload: str) -> list[Diagnostic]:
    """mypy --output json emits one JSON object per line."""
    diagnostics: list[Diagnostic] = []
    for line in payload.splitlines():
        item = _json_object(line)
        if item is None or item.get("severity") == "note":
            continue
        diagnostics.append(
            Diagnostic(
                file=item["file"],
                line=item["line"],
                symbol=item.get("code"),
                message=f"[mypy {item.get('code', '')}] {item['message']}",
            )
        )
    return diagnostics


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    targets = ctx.tool_targets()
    if not targets:
        return GateResult(gate=name, passed=True, threshold="clean", actual="no files")

    ruff = run_cmd(["ruff", "check", "--output-format", "json", *targets], cwd=ctx.project_root)
    try:
        diagnostics = parse_ruff(ruff.stdout)
    except json.JSONDecodeError:
        return GateResult(
            gate=name, passed=False, threshold="clean", actual=None,
            error=f"ruff output unparsable: {ruff.stderr.strip()[:500]}",
        )

    mypy = run_cmd(
        [sys.executable, "-m", "mypy", "--output", "json", "--no-error-summary", *targets],
        cwd=ctx.project_root,
    )
    diagnostics += parse_mypy(mypy.stdout)
    return GateResult(
        gate=name, passed=not diagnostics, threshold="clean",
        actual=f"{len(diagnostics)} findings", diagnostics=diagnostics,
    )
