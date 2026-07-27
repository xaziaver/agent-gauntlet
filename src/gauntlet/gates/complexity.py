from __future__ import annotations

from typing import Any

from gauntlet import artifacts
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "complexity"


def _symbol(block: dict[str, Any]) -> str:
    classname = block.get("classname")
    return f"{classname}.{block['name']}" if classname else str(block["name"])


def _diagnostic(file: str, block: dict[str, Any], ceiling: int) -> Diagnostic:
    symbol = artifacts.radon_symbol(block)
    score = block["complexity"]
    return Diagnostic(
        file=file,
        symbol=symbol,
        line=block["lineno"],
        value=score,
        message=(
            f"{symbol} has cyclomatic complexity {score} (max {ceiling}). "
            f"Extract the branching logic into helper functions until it is <= {ceiling}."
        ),
    )


def judge(data: dict[str, Any], ceiling: int) -> tuple[int, list[Diagnostic]]:
    """radon --json payload -> (worst CC, diagnostics). Pure, so it is unit-testable."""
    worst = 0
    diagnostics: list[Diagnostic] = []
    for file, blocks in data.items():
        if not isinstance(blocks, list):  # radon reports per-file parse errors as a dict
            continue
        for block in blocks:
            worst = max(worst, block["complexity"])
            if block["complexity"] > ceiling:
                diagnostics.append(_diagnostic(file, block, ceiling))
    return worst, diagnostics


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    ceiling = int(config.get("max", 6))
    try:
        data = artifacts.radon_blocks(ctx)
    except artifacts.ArtifactError as exc:
        return GateResult(gate=name, passed=False, threshold=ceiling, actual=None, error=str(exc))

    worst, diagnostics = judge(data, ceiling)
    return GateResult(
        gate=name, passed=not diagnostics, threshold=ceiling, actual=worst, diagnostics=diagnostics
    )
