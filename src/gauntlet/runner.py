"""Gate execution: turning a config into a list of GateResults.

Separated from cli.py so the CLI holds command definitions and this holds the
machinery they share. Nothing here knows about typer or exit codes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from gauntlet import config as config_mod
from gauntlet import events
from gauntlet.adapters import python as python_adapter
from gauntlet.gates import (
    acceptance,
    base,
    boundary,
    complexity,
    coverage,
    crap,
    duplication,
    mutation,
    protect,
    size,
    static,
    tests,
)

REGISTRY: dict[str, base.Gate] = {
    module.name: module
    for module in (
        protect,
        static,
        size,
        complexity,
        boundary,
        tests,
        coverage,
        crap,
        duplication,
        mutation,
        acceptance,
    )
}


def porcelain_path(root: Path, line: str) -> Path:
    """`XY path` or `XY old -> new` -> absolute path."""
    return (root / line[3:].strip().split(" -> ")[-1]).resolve()


def changed_python_files(root: Path) -> list[Path]:
    """Files changed vs HEAD: staged, unstaged, and untracked.

    -uall matters: without it git collapses untracked directories to a single
    entry ("?? src/"), so newly created files would never be analyzed.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    candidates = (porcelain_path(root, line) for line in proc.stdout.splitlines())
    return [path for path in candidates if base.is_analyzable(path)]


def build_context(
    root: Path, cfg: config_mod.Config, selected: list[str], changed: bool
) -> base.GateContext:
    return base.GateContext(
        project_root=root,
        src=cfg.src,
        tests=cfg.tests,
        changed_files=changed_python_files(root) if changed else None,
        enabled_gates=selected,
        verified_paths=cfg.verified_paths,
        python=python_adapter.interpreter(root, cfg.python),
    )


def run_gates(
    ctx: base.GateContext,
    cfg: config_mod.Config,
    selected: list[str],
    fail_fast: bool,
    log: events.Log | None = None,
) -> list[base.GateResult]:
    sink = log or events.disabled()
    results: list[base.GateResult] = []
    for gate_name in selected:
        result = REGISTRY[gate_name].run(ctx, cfg.gates.get(gate_name, {}))
        results.append(result)
        sink.emit(
            events.GATE_FINISHED,
            gate=result.gate,
            passed=result.passed,
            actual=result.actual,
            duration=result.duration,
            diagnostics=len(result.diagnostics),
            error=result.error,
        )
        if fail_fast and not result.passed:
            break
    return results


def run_full_gauntlet(
    root: Path,
    cfg: config_mod.Config,
    selected: list[str],
    log: events.Log | None = None,
    *,
    fail_fast: bool = False,
) -> list[base.GateResult]:
    """Every selected gate over the whole tree — never --changed.

    With nothing changed, --changed passes vacuously. That is right for edit-time
    feedback and wrong for "are you actually done".
    """
    ctx = build_context(root, cfg, selected, changed=False)
    return run_gates(ctx, cfg, selected, fail_fast, log)
