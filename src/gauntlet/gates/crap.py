"""CRAP gate: joins per-function complexity with per-function coverage.

    CRAP = CC**2 * (1 - coverage)**3 + CC

The cubic term encodes the judgement: complexity is acceptable only when proven.
At full coverage CRAP collapses to CC; at zero coverage complexity is punished
quadratically. Complexity and coverage gates in isolation miss the dangerous
intersection — an untested complex function inside a well-covered file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import artifacts
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "crap"

DEFAULT_CEILING = 15.0


@dataclass(frozen=True)
class FunctionCrap:
    file: str
    symbol: str
    line: int
    complexity: int
    coverage: float
    score: float


def crap_score(complexity: int, coverage: float) -> float:
    return round(complexity**2 * (1 - coverage) ** 3 + complexity, 2)


def required_coverage(complexity: int, ceiling: float) -> float | None:
    """Coverage that would bring this function under the ceiling, or None if impossible.

    Above CC == ceiling no amount of testing helps: CRAP is never less than CC.
    """
    if complexity > ceiling:
        return None
    headroom = (ceiling - complexity) / complexity**2
    return max(0.0, 1.0 - math.pow(headroom, 1 / 3))


def normalize(path_str: str, root: Path) -> str:
    """Key the join on root-relative POSIX strings.

    radon reports paths as invoked (often absolute), coverage.py reports them
    relative. POSIX separators keep these keys comparable with guard.py's on
    every platform.
    """
    path = Path(path_str)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def span_coverage(block: dict[str, Any], executed: set[int], missing: set[int]) -> float:
    """Coverage of one function: executed statements / all statements in its line span.

    Physical lines are the wrong denominator — blanks, comments and continuation
    lines are not statements, and counting them would understate coverage badly.
    """
    start = int(block["lineno"])
    end = int(block.get("endline", start))
    span = set(range(start, end + 1))
    covered = len(span & executed)
    total = covered + len(span & missing)
    if total == 0:
        return 1.0
    return covered / total


def _score(path: str, block: dict[str, Any], executed: set[int], missing: set[int]) -> FunctionCrap:
    coverage = span_coverage(block, executed, missing)
    complexity = int(block["complexity"])
    return FunctionCrap(
        file=path,
        symbol=artifacts.radon_symbol(block),
        line=int(block["lineno"]),
        complexity=complexity,
        coverage=round(coverage, 4),
        score=crap_score(complexity, coverage),
    )


def _file_scores(
    path: str, blocks: list[dict[str, Any]], info: dict[str, Any]
) -> list[FunctionCrap]:
    executed = set(info.get("executed_lines", []))
    missing = set(info.get("missing_lines", []))
    return [
        _score(path, block, executed, missing)
        for block in blocks
        if block.get("type") in artifacts.FUNCTION_TYPES
    ]


def crap_scores(
    cc_blocks: dict[str, Any], coverage_files: dict[str, Any], root: Path
) -> list[FunctionCrap]:
    """The join. Files radon saw but coverage did not are skipped, not scored as zero."""
    by_path = {normalize(p, root): info for p, info in coverage_files.items()}
    scores: list[FunctionCrap] = []
    for raw_path, blocks in cc_blocks.items():
        path = normalize(raw_path, root)
        info = by_path.get(path)
        if info is None or not isinstance(blocks, list):
            continue
        scores.extend(_file_scores(path, blocks, info))
    return scores


def _remedy(score: FunctionCrap, ceiling: float) -> str:
    needed = required_coverage(score.complexity, ceiling)
    if needed is None:
        return (
            f"Its complexity ({score.complexity}) exceeds the ceiling on its own — "
            f"extract functions; tests alone cannot fix this."
        )
    return f"Either cover it to at least {needed:.0%} or extract functions to reduce complexity."


def _diagnostic(score: FunctionCrap, ceiling: float) -> Diagnostic:
    return Diagnostic(
        file=score.file,
        symbol=score.symbol,
        line=score.line,
        value=score.score,
        message=(
            f"{score.symbol} has CRAP {score.score} (max {ceiling}) — complexity "
            f"{score.complexity} at {score.coverage:.0%} coverage. {_remedy(score, ceiling)}"
        ),
    )


def judge(scores: list[FunctionCrap], ceiling: float) -> tuple[float, list[Diagnostic]]:
    worst = max((s.score for s in scores), default=0.0)
    over = sorted((s for s in scores if s.score > ceiling), key=lambda s: -s.score)
    return worst, [_diagnostic(s, ceiling) for s in over]


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    ceiling = float(config.get("max", DEFAULT_CEILING))
    try:
        blocks = artifacts.radon_blocks(ctx)
        coverage_files = artifacts.load_coverage(ctx.project_root).get("files", {})
    except artifacts.ArtifactError as exc:
        return GateResult(gate=name, passed=False, threshold=ceiling, actual=None, error=str(exc))

    worst, diagnostics = judge(crap_scores(blocks, coverage_files, ctx.project_root), ceiling)
    return GateResult(
        gate=name,
        passed=not diagnostics,
        threshold=ceiling,
        actual=worst,
        diagnostics=diagnostics,
    )
