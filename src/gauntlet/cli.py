"""Gauntlet CLI.

Command definitions only. Shared plumbing lives in cli_support; the spec
sub-app lives in cli_specs. Exit codes are the agent contract:
    0  all selected gates passed
    1  gauntlet could not run (bad config, unknown gate)
    2  gates failed  <- Claude Code's "block and show stderr" convention
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import typer

from gauntlet import config as config_mod
from gauntlet import events, report, runner
from gauntlet import stop as stop_mod
from gauntlet import tree as tree_mod
from gauntlet import verdict as verdict_mod
from gauntlet.cli_approvals import lock, verify
from gauntlet.cli_doctor import doctor, version
from gauntlet.cli_events import events_app
from gauntlet.cli_loop import loop_app
from gauntlet.cli_mutants import mutant_app
from gauntlet.cli_review import review_app
from gauntlet.cli_setup import guard, init
from gauntlet.cli_specs import spec_app
from gauntlet.cli_status import status_app
from gauntlet.cli_support import EXIT_CONFIG_ERROR as EXIT_CONFIG_ERROR
from gauntlet.cli_support import EXIT_GATE_FAILURE, EXIT_OK
from gauntlet.cli_support import fail as _fail
from gauntlet.cli_support import resolve_config as _resolve_config
from gauntlet.cli_support import select_gates as _select_gates
from gauntlet.cli_verdict import verdict_app
from gauntlet.gates import base
from gauntlet.gates.base import RunInProgressError, exclusive_run

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.command("lock")(lock)
app.command("verify")(verify)
app.command("doctor")(doctor)
app.command("version")(version)
app.command("init")(init)
app.command("guard")(guard)
app.add_typer(loop_app, name="loop")
app.add_typer(spec_app, name="spec")
app.add_typer(mutant_app, name="mutant")
app.add_typer(events_app, name="events")
app.add_typer(status_app, name="status")
app.add_typer(review_app, name="review")
app.add_typer(verdict_app, name="verdict")


@app.callback()
def main() -> None:
    """Gauntlet — deterministic quality gates for AI coding agents."""


def _locked_run(root: Path, execute: Callable[[], list[base.GateResult]]) -> list[base.GateResult]:
    """Execute gates under the project lock, or exit 0 if another run holds it.

    Runs share the .gauntlet artifacts, so interleaving reports failures that are
    not real. A concurrent run is not a gate failure: exit 0 rather than blocking
    a hook on somebody else's run.
    """
    try:
        with exclusive_run(root):
            return execute()
    except RunInProgressError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=EXIT_OK) from None


def _finish(
    log: events.Log, results: list[base.GateResult], run: tree_mod.Invocation
) -> events.Event | None:
    """Close the run in the log; remember the tree only when the run was wholly green."""
    _emit_approval_needed(log, results)
    finished = log.emit(events.RUN_FINISHED, **tree_mod.finished_fields(run, results))
    tree_mod.remember(run, results, finished)
    return finished


def _read_stop_payload() -> dict[str, Any]:
    """The Stop hook's JSON. A malformed payload degrades to an unkeyed session."""
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _emit(results: list[base.GateResult], max_diags: int, json_out: bool) -> NoReturn:
    ok = report.passed(results)
    render = report.to_json if json_out else report.to_human
    # Failures go to stderr: agent hooks feed stderr back into the model's context.
    typer.echo(render(results, max_diags), err=not ok)
    raise typer.Exit(code=EXIT_OK if ok else EXIT_GATE_FAILURE)


def _stop_outcome(root: Path, session: str, passed: bool) -> int:
    """Update this session's attempt count. Returns the new count; 0 when passing."""
    attempts_file = stop_mod.attempts_path(root)
    state = stop_mod.load_attempts(attempts_file)
    if passed:
        stop_mod.save_attempts(stop_mod.clear_session(state, session), attempts_file)
        return 0
    state, count = stop_mod.record_failure(state, session)
    stop_mod.save_attempts(state, attempts_file)
    return count


def _escalate_or_bounce(
    count: int, max_attempts: int, lines: str, log: events.Log, session: str
) -> NoReturn:
    if stop_mod.should_escalate(count, max_attempts):
        log.emit(events.AGENT_ESCALATED, session=session, attempts=count)
        typer.echo(json.dumps({"systemMessage": stop_mod.escalation_message(count, lines)}))
        raise typer.Exit(code=EXIT_OK)
    typer.echo(lines, err=True)
    raise typer.Exit(code=EXIT_GATE_FAILURE)


def _emit_approval_needed(log: events.Log, results: list[base.GateResult]) -> None:
    """The dashboard inbox: findings only a human can clear."""
    for result in results:
        if result.gate not in ("protect", "acceptance") or result.passed:
            continue
        for diagnostic in result.diagnostics:
            if diagnostic.symbol in ("unapproved", "modified", "missing"):
                log.emit(
                    events.APPROVAL_NEEDED,
                    gate=result.gate,
                    subject=diagnostic.file,
                    status=diagnostic.symbol,
                )


@app.command()
def check(
    gates: str = typer.Option("", help="Comma-separated subset, e.g. static,size"),
    changed: bool = typer.Option(False, "--changed", help="Only analyze changed files"),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop at the first failing gate"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable report"),
    record: Path | None = typer.Option(None, "--record", help=verdict_mod.RECORD_HELP),
) -> None:
    """Run the configured gates and report."""
    root, cfg = _resolve_config()
    selected = _select_gates(gates, cfg)
    if record is not None and (reason := verdict_mod.refusal(record, root, cfg)) is not None:
        _fail(reason)
    log = events.Log(root)
    ctx = runner.build_context(root, cfg, selected, changed)
    run = tree_mod.Invocation(root, cfg, "check", tree_mod.measure(root, cfg), changed)

    def execute() -> list[base.GateResult]:
        log.emit(events.RUN_STARTED, command=run.command, gates=selected, changed=run.changed)
        return runner.run_gates(ctx, cfg, selected, fail_fast, log)

    results = _locked_run(root, execute)
    finished = _finish(log, results, run)
    verdict_mod.record(record, results, run, selected, finished, log.run)
    _emit(results, cfg.max_diagnostics, json_out)


def _reuse(log: events.Log, session: str, record: tree_mod.GreenRecord, root: Path) -> NoReturn:
    """The skip: one event naming the run deferred to, one line, a pass for the session."""
    log.emit(events.RUN_REUSED, **tree_mod.reused_fields(record))
    typer.echo(tree_mod.skip_line(record))
    _stop_outcome(root, session, passed=True)
    raise typer.Exit(code=EXIT_OK)


def _stop_gates(
    root: Path, cfg: config_mod.Config, log: events.Log, session: str, fail_fast: bool, skip: bool
) -> list[base.GateResult]:
    """Skip on a matching record; else every enabled gate under the lock, boundaries inside it."""
    run = tree_mod.Invocation(root, cfg, "stop-check", tree_mod.measure(root, cfg))
    record = tree_mod.reusable(run) if skip else None
    if record is not None:
        _reuse(log, session, record, root)
    selected = _select_gates("", cfg)

    def execute() -> list[base.GateResult]:
        log.emit(events.RUN_STARTED, command=run.command, gates=selected, changed=run.changed)
        return runner.run_full_gauntlet(root, cfg, selected, log, fail_fast=fail_fast)

    results = _locked_run(root, execute)
    _finish(log, results, run)
    return results


@app.command(name="stop-check")
def stop_check(
    max_attempts: int = typer.Option(
        stop_mod.DEFAULT_MAX_ATTEMPTS, help="Bounce the agent at most this many times"
    ),
    fail_fast: bool = typer.Option(
        True, "--fail-fast/--no-fail-fast", help="Stop at the first failing gate"
    ),
    skip_unchanged: bool = typer.Option(
        True, "--skip-unchanged/--no-skip-unchanged", help=tree_mod.SKIP_HELP
    ),
) -> None:
    """Stop hook: run the full gauntlet, bounded by a per-session retry cap.

    Exit 2 means not finished, report fed back; at the cap, exit 0 with a systemMessage.
    """
    root, cfg = _resolve_config()
    session = stop_mod.session_id(_read_stop_payload())
    log = events.Log(root)
    results = _stop_gates(root, cfg, log, session, fail_fast, skip_unchanged)
    count = _stop_outcome(root, session, report.passed(results))
    if count == 0:
        raise typer.Exit(code=EXIT_OK)
    report_text = report.to_human(results, cfg.max_diagnostics)
    _escalate_or_bounce(count, max_attempts, report_text, log, session)


if __name__ == "__main__":
    app()
