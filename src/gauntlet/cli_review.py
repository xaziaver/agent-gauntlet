"""The `gauntlet review` command: walk the approval inbox.

The only interactive surface in Gauntlet. Gates never prompt; a person choosing
to review does.
"""

from __future__ import annotations

from pathlib import Path

import typer

from gauntlet import events, locking, registry, review
from gauntlet import status as status_mod
from gauntlet.cli_support import EXIT_OK, fail, resolve_config

review_app = typer.Typer(no_args_is_help=False, help="Walk pending approvals one at a time.")

PROMPT = "approve / skip / quit"
CHOICES = {"a": review.Answer.APPROVE, "s": review.Answer.SKIP, "q": review.Answer.QUIT}


def _show(item: review.Item, index: int, total: int) -> None:
    typer.echo(f"\n─── {index}/{total}  {item.title}")
    typer.echo(item.body)


def _ask() -> review.Answer:
    while True:
        answer = typer.prompt(f"{PROMPT} [a/s/q]", default="s").strip().lower()[:1]
        if answer in CHOICES:
            return CHOICES[answer]
        typer.echo("Please answer a, s, or q.")


def _record(root: Path, item: review.Item, reason: str, reviewer: str) -> None:
    registry.save(review.apply(root, item, reason, reviewer), locking.lock_path(root))
    if item.stale:  # a removal is not a grant
        return
    events.Log(root).emit(
        events.APPROVAL_GRANTED,
        subject=item.pending.subject,
        namespace=item.pending.namespace,
    )


def _decide(item: review.Item, yes: bool) -> tuple[review.Answer, str]:
    """The answer and its reason. --yes takes every item without asking, except a
    mutant: an empty reason on one is the rubber stamp the ledger exists to prevent;
    and a stale approval: after a `git mv` removing it deletes every judgment it held."""
    if yes:
        withheld = item.mutant is not None or item.stale
        return (review.Answer.SKIP if withheld else review.Answer.APPROVE), ""
    answer = _ask()
    if answer is not review.Answer.APPROVE:
        return answer, ""
    if not item.needs_reason:
        return answer, ""
    # A changed threshold is the one thing a future reader will ask "why?" about.
    return answer, typer.prompt("reason (required)")


def _walk(root: Path, items: list[review.Item], yes: bool, reviewer: str) -> tuple[int, int, int]:
    """How many were approved, how many mutants --yes skipped for want of a reason,
    and how many stale approvals it skipped rather than remove."""
    approved = withheld = stale = 0
    for index, item in enumerate(items, start=1):
        _show(item, index, len(items))
        answer, reason = _decide(item, yes)
        if answer is review.Answer.QUIT:
            break
        if answer is review.Answer.APPROVE:
            _record(root, item, reason, reviewer)
            approved += 1
        elif yes:  # --yes skipped it: a stale approval, or a mutant wanting a reason
            stale += int(item.stale)
            withheld += int(not item.stale)
    return approved, withheld, stale


def _closing(approved: int, total: int, withheld: int, stale: int) -> str:
    line = f"\napproved {approved} of {total} item(s)"
    if withheld:
        line = (
            f"{line}. {withheld} mutant(s) skipped: each needs its own reason, and "
            f"`gauntlet review` without --yes asks for it."
        )
    if stale:
        joint = " " if withheld else ". "
        line += (
            f"{joint}{stale} stale approval(s) skipped: removing one is a judgment "
            f"--yes does not make"
        )
    return line


@review_app.callback(invoke_without_command=True)
def review_command(
    reviewer: str = typer.Option("", help="Recorded alongside each approval"),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Approve everything without prompting, except mutants and stale approvals",
    ),
) -> None:
    """Review what is waiting on you, one item at a time."""
    root, cfg = resolve_config()
    try:
        items = [review.build_item(root, p) for p in status_mod.pending(root, cfg)]
    except (registry.RegistryError, review.SurvivorGoneError) as exc:
        fail(str(exc))
    if not items:
        typer.echo("nothing needs your approval")
        raise typer.Exit(code=EXIT_OK)
    approved, withheld, stale = _walk(root, items, yes, reviewer)
    typer.echo(_closing(approved, len(items), withheld, stale))
    raise typer.Exit(code=EXIT_OK)
