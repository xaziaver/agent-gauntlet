"""Shared CLI plumbing, so command modules stay thin.

Exit codes are the agent contract:
    0  passed
    1  gauntlet could not run (bad config, unknown gate)
    2  gates failed  <- Claude Code's "block and show stderr" convention
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from gauntlet import config as config_mod
from gauntlet import registry, runner

EXIT_OK, EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE = 0, 1, 2


def fail(message: str) -> NoReturn:
    typer.echo(f"config error: {message}", err=True)
    raise typer.Exit(code=EXIT_CONFIG_ERROR)


def resolve_config() -> tuple[Path, config_mod.Config]:
    try:
        root = config_mod.find_root()
        return root, config_mod.load(root)
    except config_mod.ConfigError as exc:
        fail(str(exc))


def load_registry(path: Path) -> registry.Registry:
    try:
        return registry.load(path)
    except registry.RegistryError as exc:
        fail(str(exc))


def emit_findings(findings: list[registry.Finding], total: int, lock_name: str) -> NoReturn:
    if not findings:
        typer.echo(f"verified {total} path(s) against {lock_name}")
        raise typer.Exit(code=EXIT_OK)
    for finding in findings:
        typer.echo(registry.describe(finding), err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)


def parse_gate_list(requested: str) -> list[str]:
    return [g.strip() for g in requested.split(",") if g.strip()]


def select_gates(requested: str, cfg: config_mod.Config) -> list[str]:
    selected = parse_gate_list(requested) or cfg.enabled_gates
    if not selected:
        fail("no gates enabled — add [gates.*] tables to gauntlet.toml.")
    unknown = sorted(set(selected) - set(runner.REGISTRY))
    if unknown:
        fail(f"unknown gate(s) {unknown}. Available: {sorted(runner.REGISTRY)}")
    return selected
