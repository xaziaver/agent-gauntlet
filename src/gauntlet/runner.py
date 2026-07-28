"""Gate execution: turning a config into a list of GateResults.

Separated from cli.py so the CLI holds command definitions and this holds the
machinery they share. Nothing here knows about typer or exit codes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from gauntlet import config as config_mod
from gauntlet.gates import (
    base,
    complexity,
    coverage,
    crap,
    duplication,
    protect,
    size,
    static,
    tests,
)

REGISTRY: dict[str, base.Gate] = {
    module.name: module
    for module in (protect, static, size, complexity, tests, coverage, crap, duplication)
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
    )


def run_gates(
    ctx: base.GateContext, cfg: config_mod.Config, selected: list[str], fail_fast: bool
) -> list[base.GateResult]:
    results: list[base.GateResult] = []
    for gate_name in selected:
        results.append(REGISTRY[gate_name].run(ctx, cfg.gates.get(gate_name, {})))
        if fail_fast and not results[-1].passed:
            break
    return results


def run_full_gauntlet(
    root: Path, cfg: config_mod.Config, selected: list[str]
) -> list[base.GateResult]:
    """Every selected gate over the whole tree — never --changed.

    With nothing changed, --changed passes vacuously. That is right for edit-time
    feedback and wrong for "are you actually done".
    """
    return run_gates(build_context(root, cfg, selected, changed=False), cfg, selected, False)
