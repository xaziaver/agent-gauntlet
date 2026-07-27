"""Gauntlet CLI.

Exit codes are the agent contract:
    0  all selected gates passed
    1  gauntlet could not run (bad config, unknown gate)
    2  gates failed  <- Claude Code's "block and show stderr" convention
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NoReturn

import typer

from gauntlet import __version__
from gauntlet import config as config_mod
from gauntlet import report
from gauntlet.gates import base, complexity, coverage, size, static, tests

EXIT_OK, EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE = 0, 1, 2

REGISTRY: dict[str, base.Gate] = {
    module.name: module  # type: ignore[misc]
    for module in (static, size, complexity, tests, coverage)
}

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@app.callback()
def main() -> None:
    """Gauntlet — deterministic quality gates for AI coding agents."""


def _fail(message: str) -> NoReturn:
    typer.echo(f"config error: {message}", err=True)
    raise typer.Exit(code=EXIT_CONFIG_ERROR)


def _porcelain_path(root: Path, line: str) -> Path:
    """`XY path` or `XY old -> new` -> absolute path."""
    return (root / line[3:].strip().split(" -> ")[-1]).resolve()


def _changed_python_files(root: Path) -> list[Path]:
    """Files changed vs HEAD: staged, unstaged, and untracked."""
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return []
    candidates = (_porcelain_path(root, line) for line in proc.stdout.splitlines())
    return [path for path in candidates if base.is_analyzable(path)]


def _resolve_config() -> tuple[Path, config_mod.Config]:
    try:
        root = config_mod.find_root()
        return root, config_mod.load(root)
    except config_mod.ConfigError as exc:
        _fail(str(exc))


def _parse_gate_list(requested: str) -> list[str]:
    return [g.strip() for g in requested.split(",") if g.strip()]


def _select_gates(requested: str, cfg: config_mod.Config) -> list[str]:
    selected = _parse_gate_list(requested) or cfg.enabled_gates
    if not selected:
        _fail("no gates enabled — add [gates.*] tables to gauntlet.toml.")
    unknown = sorted(set(selected) - set(REGISTRY))
    if unknown:
        _fail(f"unknown gate(s) {unknown}. Available: {sorted(REGISTRY)}")
    return selected


def _run_gates(
    ctx: base.GateContext, cfg: config_mod.Config, selected: list[str], fail_fast: bool
) -> list[base.GateResult]:
    results: list[base.GateResult] = []
    for gate_name in selected:
        results.append(REGISTRY[gate_name].run(ctx, cfg.gates.get(gate_name, {})))
        if fail_fast and not results[-1].passed:
            break
    return results


def _emit(results: list[base.GateResult], max_diags: int, json_out: bool) -> NoReturn:
    ok = report.passed(results)
    render = report.to_json if json_out else report.to_human
    # Failures go to stderr: agent hooks feed stderr back into the model's context.
    typer.echo(render(results, max_diags), err=not ok)
    raise typer.Exit(code=EXIT_OK if ok else EXIT_GATE_FAILURE)


@app.command()
def check(
    gates: str = typer.Option("", help="Comma-separated subset, e.g. static,size"),
    changed: bool = typer.Option(False, "--changed", help="Only analyze changed files"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop at the first failing gate"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable report"),
) -> None:
    """Run the configured gates and report."""
    root, cfg = _resolve_config()
    selected = _select_gates(gates, cfg)
    ctx = base.GateContext(
        project_root=root,
        src=cfg.src,
        tests=cfg.tests,
        changed_files=_changed_python_files(root) if changed else None,
        enabled_gates=selected,
    )
    _emit(_run_gates(ctx, cfg, selected, fail_fast), cfg.max_diagnostics, json_out)


@app.command()
def version() -> None:
    """Print the gauntlet version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
