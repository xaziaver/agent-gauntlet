"""Protect gate: the approved configuration must not have changed.

Route-independent where the PreToolUse guard is not. The guard only sees
file-path tools, so a shell redirect, an editor, or a subagent bypasses it
entirely; comparing content against approved hashes catches all of them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gauntlet import locking, registry
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "protect"

THRESHOLD = "approved and unchanged"


def _diagnostic(finding: registry.Finding) -> Diagnostic:
    return Diagnostic(
        file=registry.bare(finding.key),
        symbol=finding.status.value,
        message=registry.describe(finding),
    )


def _missing_lock_diagnostic(lock: Path) -> Diagnostic:
    return Diagnostic(
        file=lock.name,
        message=(
            f"{lock.name} is missing and require_lock is set. A human must run "
            f"`gauntlet lock` to record which configuration is approved."
        ),
    )


def _unlocked(require_lock: bool, lock: Path) -> GateResult:
    """No lock file yet.

    Fails open by default so that installing Gauntlet does not immediately break
    a project. Set require_lock = true once the approvals are recorded.
    """
    if require_lock:
        return GateResult(
            gate=name,
            passed=False,
            threshold=THRESHOLD,
            actual="not locked",
            diagnostics=[_missing_lock_diagnostic(lock)],
        )
    return GateResult(
        gate=name,
        passed=True,
        threshold=THRESHOLD,
        actual=f"not locked — run `gauntlet lock` to create {lock.name}",
    )


def _result(findings: list[registry.Finding], total: int) -> GateResult:
    return GateResult(
        gate=name,
        passed=not findings,
        threshold=THRESHOLD,
        actual=f"{total - len(findings)}/{total} paths unchanged",
        diagnostics=[_diagnostic(f) for f in findings],
    )


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    lock = locking.lock_path(ctx.project_root)
    if not lock.exists():
        return _unlocked(bool(config.get("require_lock", False)), lock)

    try:
        approved = registry.load(lock)
    except registry.RegistryError as exc:
        return GateResult(gate=name, passed=False, threshold=THRESHOLD, actual=None, error=str(exc))

    findings = locking.verify_config(ctx.project_root, ctx.verified_paths, approved)
    return _result(findings, len(ctx.verified_paths))
