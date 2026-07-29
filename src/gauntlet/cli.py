"""Gauntlet CLI.

Exit codes are the agent contract:
    0  all selected gates passed
    1  gauntlet could not run (bad config, unknown gate)
    2  gates failed  <- Claude Code's "block and show stderr" convention
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, NoReturn

import typer

from gauntlet import __version__, locking, registry, report, runner, scaffold
from gauntlet import config as config_mod
from gauntlet import doctor as doctor_mod
from gauntlet import guard as guard_mod
from gauntlet import stop as stop_mod
from gauntlet.gates import base

AGENTS = ("claude-code", "generic")

EXIT_OK, EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE = 0, 1, 2


app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


@app.callback()
def main() -> None:
    """Gauntlet — deterministic quality gates for AI coding agents."""


def _fail(message: str) -> NoReturn:
    typer.echo(f"config error: {message}", err=True)
    raise typer.Exit(code=EXIT_CONFIG_ERROR)


def _resolve_config() -> tuple[Path, config_mod.Config]:
    try:
        root = config_mod.find_root()
        return root, config_mod.load(root)
    except config_mod.ConfigError as exc:
        _fail(str(exc))


def _read_stop_payload() -> dict[str, Any]:
    """The Stop hook's JSON. A malformed payload degrades to an unkeyed session."""
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_gate_list(requested: str) -> list[str]:
    return [g.strip() for g in requested.split(",") if g.strip()]


def _select_gates(requested: str, cfg: config_mod.Config) -> list[str]:
    selected = _parse_gate_list(requested) or cfg.enabled_gates
    if not selected:
        _fail("no gates enabled — add [gates.*] tables to gauntlet.toml.")
    unknown = sorted(set(selected) - set(runner.REGISTRY))
    if unknown:
        _fail(f"unknown gate(s) {unknown}. Available: {sorted(runner.REGISTRY)}")
    return selected


def _emit(results: list[base.GateResult], max_diags: int, json_out: bool) -> NoReturn:
    ok = report.passed(results)
    render = report.to_json if json_out else report.to_human
    # Failures go to stderr: agent hooks feed stderr back into the model's context.
    typer.echo(render(results, max_diags), err=not ok)
    raise typer.Exit(code=EXIT_OK if ok else EXIT_GATE_FAILURE)


def _load_registry(path: Path) -> registry.Registry:
    try:
        return registry.load(path)
    except registry.RegistryError as exc:
        _fail(str(exc))


def _emit_findings(findings: list[registry.Finding], total: int, lock_name: str) -> NoReturn:
    if not findings:
        typer.echo(f"verified {total} path(s) against {lock_name}")
        raise typer.Exit(code=EXIT_OK)
    for finding in findings:
        typer.echo(registry.describe(finding), err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)


def _escalate_or_bounce(count: int, max_attempts: int, lines: str) -> NoReturn:
    if stop_mod.should_escalate(count, max_attempts):
        typer.echo(json.dumps({"systemMessage": stop_mod.escalation_message(count, lines)}))
        raise typer.Exit(code=EXIT_OK)
    typer.echo(lines, err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)


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
    ctx = runner.build_context(root, cfg, selected, changed)
    _emit(runner.run_gates(ctx, cfg, selected, fail_fast), cfg.max_diagnostics, json_out)


@app.command()
def guard() -> None:
    """PreToolUse hook: block edits to protected paths. Reads hook JSON on stdin.

    Exit 2 blocks the tool call and shows the message to the agent. Exit 1 is a
    non-blocking error in Claude Code, so a broken config means the guard simply
    does not apply rather than wedging the agent.
    """
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

    message = guard_mod.decide(payload, root, cfg.protected_paths)
    if message is None:
        raise typer.Exit(code=EXIT_OK)
    typer.echo(message, err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)


@app.command()
def init(
    agent: str = typer.Option("claude-code", help=f"One of: {', '.join(AGENTS)}"),
    fast_gates: str = typer.Option(scaffold.FAST_GATES, help="Gates for the edit-time hook"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would change, write nothing"),
) -> None:
    """Generate agent hooks or CI integration for this project."""
    if agent not in AGENTS:
        _fail(f"unknown agent {agent!r}. Available: {list(AGENTS)}")
    root, _ = _resolve_config()

    for path, content in scaffold.plan(root, agent, fast_gates):
        if dry_run:
            typer.echo(f"would write  {path}\n{content}")
            continue
        typer.echo(f"{scaffold.write(root, path, content).value:<10} {path}")

    if not dry_run:
        typer.echo("\nRun `gauntlet lock` to approve the generated configuration.")


@app.command()
def lock() -> None:
    """Approve the current content of the verified paths.

    This is the deliberate human action the whole mechanism rests on: it records
    what the thresholds and configuration are *supposed* to be.
    """
    root, cfg = _resolve_config()
    try:
        updated, skipped = locking.approve_all(root, cfg.verified_paths)
        registry.save(updated, locking.lock_path(root))
    except registry.RegistryError as exc:
        _fail(str(exc))

    for key in sorted(updated.entries):
        typer.echo(f"approved  {key}")
    for key in skipped:
        typer.echo(f"skipped   {key} (does not exist)")


@app.command(name="stop-check")
def stop_check(
    max_attempts: int = typer.Option(
        stop_mod.DEFAULT_MAX_ATTEMPTS, help="Bounce the agent at most this many times"
    ),
) -> None:
    """Stop hook: run the full gauntlet, bounded by a per-session retry cap.

    Exit 2 tells Claude Code the agent is not finished and feeds the report back.
    Once the cap is reached this exits 0 with a systemMessage, handing the problem
    to the human rather than looping forever.
    """
    root, cfg = _resolve_config()
    session = stop_mod.session_id(_read_stop_payload())
    attempts_file = stop_mod.attempts_path(root)
    state = stop_mod.load_attempts(attempts_file)

    results = runner.run_full_gauntlet(root, cfg, _select_gates("", cfg))
    if report.passed(results):
        stop_mod.save_attempts(stop_mod.clear_session(state, session), attempts_file)
        raise typer.Exit(code=EXIT_OK)

    state, count = stop_mod.record_failure(state, session)
    stop_mod.save_attempts(state, attempts_file)
    _escalate_or_bounce(count, max_attempts, report.to_human(results, cfg.max_diagnostics))


@app.command()
def verify() -> None:
    """Check verified paths against their approved hashes.

    Route-independent: it catches a change made through Bash, an editor, or a
    subagent, all of which bypass the PreToolUse guard.
    """
    root, cfg = _resolve_config()
    path = locking.lock_path(root)
    if not path.exists():
        typer.echo(f"not locked — run `gauntlet lock` to record approvals in {path.name}")
        raise typer.Exit(code=EXIT_OK)

    subjects = locking.read_subjects(root, cfg.verified_paths)
    findings = locking.failures(registry.verify_all(_load_registry(path), subjects))
    _emit_findings(findings, len(subjects), path.name)


@app.command()
def doctor() -> None:
    """Check that every enabled gate's tooling is present in THIS environment.

    Run it with the same command your hooks use (bare `gauntlet doctor`, not
    `uv run gauntlet doctor`) — a broken hook environment fails open silently,
    and this is how you find out.
    """
    _, cfg = _resolve_config()
    checks = doctor_mod.run_checks(cfg.enabled_gates)
    typer.echo(doctor_mod.render(checks))
    raise typer.Exit(code=EXIT_OK if doctor_mod.healthy(checks) else EXIT_CONFIG_ERROR)    

    
@app.command()
def version() -> None:
    """Print the gauntlet version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
