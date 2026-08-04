"""Mutation gate: are the unit tests actually detecting changes to the code?

Coverage proves lines ran. This proves the tests notice when those lines behave
differently — a test that calls a function and asserts nothing produces full
coverage and kills no mutants.

Equivalent mutants are real: the Phase 0 spike hit a principled 131/133 ceiling
where two survivors provably could not change behavior. So survivors are
classified against the shared ledger rather than treated as automatic defects,
and reviewed-equivalent ones count as killed for scoring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gauntlet import config as config_mod
from gauntlet import locking, registry
from gauntlet import mutants as mutants_mod
from gauntlet.adapters import python as python_adapter
from gauntlet.adapters.python import CodeMutant
from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "mutation"

# Code mutants are keyed under one subject: their locator already carries the
# module, so a per-module subject would just repeat it.
SUBJECT = "code"

DEFAULT_MIN_SCORE = 90.0
SURVIVED = "survived"
SKIPPED_BUCKETS = ("skipped", "suspicious")
MAX_SURVIVORS_INSPECTED = 40

SHOW_TIMEOUT = 60

ARTIFACT_HINT = (
    "mutmut failed to copy the source tree. This usually means an editor lock or "
    "backup file (.#name.py, name.py~) is present — mutmut cannot copy a dangling "
    "symlink. Close the file in your editor or delete the artifact."
)


def score(killed: int, equivalent: int, unresolved: int) -> float:
    """Reviewed-equivalent mutants count as killed: no test could have killed them."""
    total = killed + equivalent + unresolved
    if total == 0:
        return 100.0
    return round(100.0 * (killed + equivalent) / total, 2)


def _filters(ctx: GateContext, config: dict[str, Any]) -> list[str] | None:
    """mutmut name filters for this run. None means "nothing changed, skip"."""
    if str(config.get("scope", "changed")) != "changed" or ctx.changed_files is None:
        return []
    if not ctx.changed_files:
        return None
    return python_adapter.module_filter(ctx.src, ctx.changed_files)


def explain(error: str) -> str:
    """Turn mutmut's traceback into something an agent can act on."""
    if "FileNotFoundError" in error and (".#" in error or "~" in error):
        return f"{ARTIFACT_HINT}\n{error}"
    return error


def collect(root: Path, python: str, names: list[str], timeout: int) -> list[CodeMutant]:
    """One `mutmut show` per survivor: the ID alone tells an agent nothing.

    Public: the `gauntlet mutant` commands must see exactly what the gate sees.
    """
    collected: list[CodeMutant] = []
    for mutant_name in names[:MAX_SURVIVORS_INSPECTED]:
        module, function = python_adapter.parse_mutant_name(mutant_name)
        removed, added = python_adapter.show_mutant(root, python, mutant_name, timeout)
        collected.append(
            CodeMutant(
                name=mutant_name, module=module, function=function, removed=removed, added=added
            )
        )
    return collected


class MutmutError(Exception):
    """mutmut could not be run."""


def survivors_for(root: Path, python: str, filters: list[str], timeout: int) -> list[CodeMutant]:
    """Run mutmut and return the survivors, fully described."""
    outcome = python_adapter.run_mutmut(root, python, filters, timeout)
    if not outcome.ok:
        raise MutmutError(explain(outcome.error))
    return collect(root, python, outcome.survivors, SHOW_TIMEOUT)


def _diagnostic(mutant: CodeMutant) -> Diagnostic:
    return Diagnostic(
        file=mutant.module.replace(".", "/") + ".py",
        symbol=mutant.function,
        message=(
            f"Surviving mutant in {mutant.function}: `{mutant.removed}` -> "
            f"`{mutant.added}`. No test failed with this change, so the behavior it "
            f"alters is untested. Add a test that fails under it — or, if the change "
            f"provably cannot alter behavior, have a human record it with "
            f"`gauntlet mutant approve-code`."
        ),
    )


def _stale_diagnostic(stale: list[str]) -> Diagnostic:
    return Diagnostic(
        file=config_mod.LOCK_FILENAME,
        message=(
            f"{len(stale)} approved equivalent mutant(s) are no longer produced — the "
            f"code or the tests changed. Remove them with `gauntlet mutant prune-code`."
        ),
    )


def _summary(actual: float, verdict: mutants_mod.Classification[CodeMutant], killed: int) -> str:
    parts = [f"score {actual}%", f"{killed} killed"]
    if verdict.failing:
        parts.append(f"{len(verdict.failing)} unresolved")
    if verdict.equivalent:
        parts.append(f"{len(verdict.equivalent)} reviewed-equivalent")
    if verdict.stale:
        parts.append(f"{len(verdict.stale)} stale approval(s)")
    return ", ".join(parts)


def _judge(
    verdict: mutants_mod.Classification[CodeMutant],
    killed: int,
    min_score: float,
    require_review: bool,
) -> GateResult:
    actual = score(killed, len(verdict.equivalent), len(verdict.failing))
    diagnostics = [_diagnostic(m) for m in verdict.failing]
    if verdict.stale:
        diagnostics.append(_stale_diagnostic(verdict.stale))
    passed = actual >= min_score and not (require_review and verdict.failing)
    return GateResult(
        gate=name,
        passed=passed,
        threshold={"min_score": min_score, "require_review": require_review},
        actual=_summary(actual, verdict, killed),
        diagnostics=diagnostics,
    )


def _classified_result(
    ctx: GateContext, outcome: python_adapter.MutationRun, min_score: float, require_review: bool
) -> GateResult:
    survivors = collect(ctx.project_root, ctx.python, outcome.survivors, SHOW_TIMEOUT)
    approved = registry.load(locking.lock_path(ctx.project_root))
    verdict = mutants_mod.classify(approved, SUBJECT, survivors)
    return _judge(verdict, outcome.total - len(outcome.survivors), min_score, require_review)


def _nothing_changed(threshold: dict[str, Any]) -> GateResult:
    return GateResult(
        gate=name, passed=True, threshold=threshold, actual="no changed modules", vacuous=True
    )


def _tool_failure(threshold: dict[str, Any], error: str) -> GateResult:
    return GateResult(
        gate=name, passed=False, threshold=threshold, actual=None, error=explain(error)[:800]
    )


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    min_score = float(config.get("min_score", DEFAULT_MIN_SCORE))
    require_review = bool(config.get("require_review", False))
    threshold = {"min_score": min_score, "require_review": require_review}

    filters = _filters(ctx, config)
    if filters is None:
        return _nothing_changed(threshold)

    timeout = int(config.get("timeout", 1800))
    outcome = python_adapter.run_mutmut(ctx.project_root, ctx.python, filters, timeout)
    if not outcome.ok:
        return _tool_failure(threshold, outcome.error)
    return _classified_result(ctx, outcome, min_score, require_review)
