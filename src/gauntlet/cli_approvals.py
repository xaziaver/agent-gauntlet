"""The `gauntlet lock` and `gauntlet verify` commands: the approval ceremony."""

from __future__ import annotations

import typer

from gauntlet import events, locking, registry
from gauntlet.cli_support import EXIT_OK, emit_findings, fail, load_registry, resolve_config

approvals_app = typer.Typer(no_args_is_help=True, help="Approve and verify configuration.")


@approvals_app.command("lock")
def lock() -> None:
    """Approve the current content of the verified paths.

    This is the deliberate human action the whole mechanism rests on: it records
    what the thresholds and configuration are *supposed* to be.
    """
    root, cfg = resolve_config()
    try:
        updated, skipped = locking.approve_all(root, cfg.verified_paths)
        registry.save(updated, locking.lock_path(root))
    except registry.RegistryError as exc:
        fail(str(exc))

    events.Log(root).emit(events.APPROVAL_GRANTED, subject="config", count=len(cfg.verified_paths))
    for key in sorted(registry.in_namespace(updated, locking.CONFIG_NAMESPACE).entries):
        typer.echo(f"approved  {registry.bare(key)}")
    for key in skipped:
        typer.echo(f"skipped   {key} (does not exist)")


@approvals_app.command("verify")
def verify() -> None:
    """Check verified paths against their approved hashes.

    Route-independent: it catches a change made through Bash, an editor, or a
    subagent, all of which bypass the PreToolUse guard.
    """
    root, cfg = resolve_config()
    path = locking.lock_path(root)
    if not path.exists():
        typer.echo(f"not locked — run `gauntlet lock` to record approvals in {path.name}")
        raise typer.Exit(code=EXIT_OK)
    findings = locking.verify_config(root, cfg.verified_paths, load_registry(path))
    emit_findings(findings, len(cfg.verified_paths), path.name)
