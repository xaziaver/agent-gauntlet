"""Static gate: lint and type checking. Says nothing about behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from gauntlet.gates.base import Diagnostic, GateContext, GateResult, run_cmd, timed

name = "static"

RUFF_OK_CODES = (0, 1)  # 0 = clean, 1 = findings; anything else is a tool failure
MYPY_OK_CODES = (0, 1)


class _ToolError(Exception):
    """A static-analysis tool produced output we cannot parse."""


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


def _ruff_diagnostics(ctx: GateContext, targets: list[str]) -> list[Diagnostic]:
    proc = run_cmd(["ruff", "check", "--output-format", "json", *targets], cwd=ctx.project_root)
    if proc.returncode not in RUFF_OK_CODES:
        # A crashed tool must not read as a clean bill of health.
        raise _ToolError(
            f"ruff exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    try:
        return parse_ruff(proc.stdout)
    except json.JSONDecodeError as exc:
        raise _ToolError(f"ruff output unparsable: {proc.stderr.strip()[:500]}") from exc


def _mypy_diagnostics(ctx: GateContext, targets: list[str]) -> list[Diagnostic]:
    proc = run_cmd(
        [
            sys.executable,
            "-m",
            "mypy",
            "--python-executable",
            ctx.python,
            "--output",
            "json",
            "--no-error-summary",
            *targets,
        ],
        cwd=ctx.project_root,
    )
    if proc.returncode not in MYPY_OK_CODES or (proc.returncode == 1 and not proc.stdout.strip()):
        # mypy exits 1 both for "errors found" (with output) and "no module named
        # mypy" (without). Silence plus a nonzero code is a broken tool, not a pass.
        raise _ToolError(
            f"mypy exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    return parse_mypy(proc.stdout)


def _no_source(src: Path) -> GateResult:
    # mypy's own message here is "There are no .py[i] files in directory", which
    # sends people looking at mypy rather than at their empty src/.
    return GateResult(
        gate=name,
        passed=True,
        threshold="clean",
        actual=f"no Python files under {src}",
        vacuous=True,
    )


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:  # noqa: ARG001
    # `config` is unused but required by the Gate protocol's uniform signature.
    if not ctx.python_files():
        return _no_source(ctx.src)

    targets = ctx.tool_targets()
    try:
        diagnostics = _ruff_diagnostics(ctx, targets) + _mypy_diagnostics(ctx, targets)
    except _ToolError as exc:
        return GateResult(gate=name, passed=False, threshold="clean", actual=None, error=str(exc))

    return GateResult(
        gate=name,
        passed=not diagnostics,
        threshold="clean",
        actual=f"{len(diagnostics)} findings",
        diagnostics=diagnostics,
    )
