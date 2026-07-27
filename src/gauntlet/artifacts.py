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
FUNCTION_TYPES = frozenset({"function", "method"})


class ArtifactError(Exception):
    """Tool output is missing or unparsable. Becomes GateResult.error, never a crash."""


def load_coverage(root: Path) -> dict[str, Any]:
    """The coverage.json written by the tests gate."""
    path = root / COVERAGE_ARTIFACT
    if not path.exists():
        raise ArtifactError(
            f"No {COVERAGE_ARTIFACT} — the tests gate must run before this gate "
            f"(check gate order / --gates selection)."
        )
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
