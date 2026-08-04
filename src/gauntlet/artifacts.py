"""Shared access to external tool output, so gates do not duplicate invocations.

Both complexity and crap need radon; both coverage and crap need the coverage
artifact. Failures raise ArtifactError, which gates turn into GateResult.error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gauntlet.gates.base import GateContext, run_cmd

COVERAGE_ARTIFACT = Path(".gauntlet") / "coverage.json"
JUNIT_ARTIFACT = Path(".gauntlet") / "junit.xml"
FUNCTION_TYPES = frozenset({"function", "method"})


class ArtifactError(Exception):
    """Tool output is missing or unparsable. Becomes GateResult.error, never a crash."""


def _missing_coverage_reason(root: Path) -> str:
    """ "The tests gate never ran" and "it ran and measured nothing" are different
    problems. Telling someone to run the tests gate when they just did sends them
    looking in the wrong place — usually it means an empty source tree."""
    if (root / JUNIT_ARTIFACT).exists():
        return (
            "The tests gate ran but wrote no coverage data. That usually means there is "
            "no Python source under [project].src for pytest-cov to measure."
        )
    return (
        f"No {COVERAGE_ARTIFACT} — the tests gate must run before this gate "
        f"(check gate order / --gates selection)."
    )


def load_coverage(root: Path) -> dict[str, Any]:
    """The coverage.json written by the tests gate."""
    path = root / COVERAGE_ARTIFACT
    if not path.exists():
        raise ArtifactError(_missing_coverage_reason(root))
    try:
        parsed: dict[str, Any] = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"{COVERAGE_ARTIFACT} unreadable: {exc}") from exc
    return parsed


def radon_blocks(ctx: GateContext) -> dict[str, Any]:
    """`radon cc --json` for this context's targets. Keys are paths as radon saw them."""
    targets = ctx.tool_targets()
    if not targets:
        return {}
    proc = run_cmd(["radon", "cc", "--json", *targets], cwd=ctx.project_root)
    if not proc.stdout.strip():
        raise ArtifactError(f"radon produced no output: {proc.stderr.strip()[:500]}")
    try:
        parsed: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"radon output unparsable: {exc}") from exc
    return parsed


def radon_symbol(block: dict[str, Any]) -> str:
    """Qualified name for a radon block: `Class.method` or `function`."""
    classname = block.get("classname")
    return f"{classname}.{block['name']}" if classname else str(block["name"])
