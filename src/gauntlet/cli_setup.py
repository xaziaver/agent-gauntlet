"""The `gauntlet init` and `gauntlet guard` commands: scaffolding and the edit-time guard."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import typer

from gauntlet import config as config_mod
from gauntlet import events, scaffold
from gauntlet import guard as guard_mod
from gauntlet.cli_support import EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE, EXIT_OK, fail

AGENTS = ("claude-code", "generic")


def _guard_context() -> tuple[Path, config_mod.Config, dict[str, Any]]:
    """Root, config, and hook payload — or exit 1, which Claude Code ignores."""
    try:
        root = config_mod.find_root()
        cfg = config_mod.load(root)
    except config_mod.ConfigError as exc:
        typer.echo(f"guard: {exc}", err=True)
        raise typer.Exit(code=EXIT_CONFIG_ERROR) from None
    try:
        payload = guard_mod.parse_payload(sys.stdin.read())
    except guard_mod.PayloadError as exc:
        typer.echo(f"guard: {exc}", err=True)
        raise typer.Exit(code=EXIT_CONFIG_ERROR) from None
    return root, cfg, payload


def guard() -> None:
    """PreToolUse hook: block edits to protected paths. Reads hook JSON on stdin.

    Exit 2 blocks the tool call and shows the message to the agent. Exit 1 is a
    non-blocking error in Claude Code, so a broken config means the guard simply
    does not apply rather than wedging the agent.
    """
    root, cfg, payload = _guard_context()
    message = guard_mod.decide(payload, root, cfg.protected_paths)
    if message is None:
        raise typer.Exit(code=EXIT_OK)
    events.Log(root).emit(
        events.AGENT_BLOCKED,
        path=guard_mod.target_path(payload),
        tool=payload.get("tool_name"),
        session=payload.get("session_id"),
    )
    typer.echo(message, err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)


def init(
    agent: str = typer.Option("claude-code", help=f"One of: {', '.join(AGENTS)}"),
    fast_gates: str = typer.Option(scaffold.FAST_GATES, help="Gates for the edit-time hook"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would change, write nothing"),
) -> None:
    """Generate config, agent hooks, or CI integration for this project."""
    if agent not in AGENTS:
        fail(f"unknown agent {agent!r}. Available: {list(AGENTS)}")
    try:
        root = config_mod.find_root()
    except config_mod.ConfigError:
        root = Path.cwd()  # a brand-new project: gauntlet.toml is about to be created

    for path, content in scaffold.plan(root, agent, fast_gates):
        if dry_run:
            typer.echo(f"would write  {path}\n{content}")
            continue
        typer.echo(f"{scaffold.write(root, path, content).value:<10} {path}")

    if not dry_run:
        typer.echo("\nReview gauntlet.toml, then run `gauntlet lock` to approve it.")
