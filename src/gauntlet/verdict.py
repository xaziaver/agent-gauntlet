"""A run's verdict as a record a repository can carry.

The event log is the only authority on what a run decided, and it lives in a
gate-writable, git-ignored file that rotates destructively. The record is one
JSON object holding a run's `gate.finished` lines as the log wrote them, a
digest over the five fields a regression pass compares, the tree the run
measured, and the harness that measured it. It is written at a path the caller
names, never under `.gauntlet/` or a gated path, and no code path reads it back:
its evidence is content, checkable against any copy of the log.

Two builders, one shape. A live run builds the record from its own results
(`from_run`), never from the log, because `_rotate` runs inside every `emit` and
a run's lines can straddle two files; `verdict export` builds it from a log
(`from_lines`) for runs already made, with the harness null: nobody recorded it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import gauntlet
from gauntlet import config as config_mod
from gauntlet import events, tree
from gauntlet.gates import base

SCHEMA_VERSION = 1
RECORD_HELP = "Write the run's verdict record to PATH (never under .gauntlet/ or a gated path)"
PACKAGE_DIR = Path(gauntlet.__file__).parent

# The `gate.finished` payload, in the runner's order; the digest's five in its own.
GATE_KEYS = ("gate", "passed", "actual", "duration", "diagnostics", "error")
DIGEST_KEYS = ("gate", "passed", "error", "diagnostics", "actual")


@dataclass(frozen=True)
class Record:
    """Decision (1)'s fields; every boundary field is null when the log has no such line."""

    run: str
    command: str | None
    changed: bool | None
    gates: list[str] | None
    finished_at: str | None
    passed: bool
    tree: str | None
    files: int | None
    verdict: list[dict[str, Any]]
    verdict_sha256: str
    harness: dict[str, Any] | None
    v: int = SCHEMA_VERSION


def _as_logged(value: Any) -> Any:
    """The value as the log serialises it, so live results and read-back lines agree."""
    return json.loads(json.dumps(value, default=str))


def digest(verdict: list[dict[str, Any]]) -> str:
    """sha256 of the canonical JSON of the five compared fields per gate, in run order."""
    tuples = [{key: _as_logged(line[key]) for key in DIGEST_KEYS} for line in verdict]
    canonical = json.dumps(tuples, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _gate_line(result: base.GateResult) -> dict[str, Any]:
    """The runner's `gate.finished` payload for one result, as the log would hold it."""
    payload = {key: getattr(result, key) for key in GATE_KEYS}
    payload["diagnostics"] = len(result.diagnostics)
    logged: dict[str, Any] = _as_logged(payload)
    return logged


def _record(run_id: str, verdict: list[dict[str, Any]], **fields: Any) -> Record:
    return Record(
        run=run_id,
        passed=all(line["passed"] for line in verdict),
        verdict=verdict,
        verdict_sha256=digest(verdict),
        **fields,
    )


def from_run(
    results: list[base.GateResult],
    run: tree.Invocation,
    gates: list[str],
    finished: events.Event | None,
    run_id: str,
) -> Record:
    """The record of this process's own run; `finished` None leaves `finished_at` null."""
    return _record(
        run_id,
        [_gate_line(result) for result in results],
        command=run.command,
        changed=run.changed,
        gates=gates,
        finished_at=None if finished is None else finished.at,
        harness=harness(),
        **tree.fields(run.measured),
    )


def lines_of(items: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """The parsed log lines of one run, in log order."""
    return [item for item in items if item.get("run") == run_id]


def deferred_to(lines: list[dict[str, Any]]) -> str | None:
    """The run a skip deferred to, when the lines are only `run.reused`; else (or on none) None."""
    if lines and all(line.get("kind") == events.RUN_REUSED for line in lines):
        return str(lines[0]["reused_run"])
    return None


class ShortGateLineError(ValueError):
    """A `gate.finished` line lacks one of its six keys: the log holds no verdict for that gate."""


def _first(lines: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    return next((line for line in lines if line.get("kind") == kind), {})


def _gate_fields(line: dict[str, Any]) -> dict[str, Any]:
    """The six `gate.finished` keys of one line, or ShortGateLineError naming the first absent."""
    for key in GATE_KEYS:
        if key not in line:
            raise ShortGateLineError(
                f"gate.finished line ({line.get('gate')!r}, {line.get('at')}) has no {key!r}"
            )
    return {key: line[key] for key in GATE_KEYS}


def from_lines(lines: list[dict[str, Any]], run_id: str) -> Record:
    """The record of a run as one log file holds it; absent boundary lines give nulls.

    Raises ShortGateLineError for a `gate.finished` line missing one of GATE_KEYS.
    """
    started = _first(lines, events.RUN_STARTED)
    finished = _first(lines, events.RUN_FINISHED)
    verdict = [_gate_fields(line) for line in lines if line.get("kind") == events.GATE_FINISHED]
    return _record(
        run_id,
        verdict,
        command=started.get("command"),
        changed=started.get("changed"),
        gates=started.get("gates"),
        finished_at=finished.get("at"),
        tree=finished.get("tree"),
        files=finished.get("files"),
        harness=None,
    )


def _package_names(package: Path) -> list[bytes]:
    """The analyzable `.py` files under the package, relative POSIX paths, bytewise sorted."""
    return sorted(
        path.relative_to(package).as_posix().encode("utf-8")
        for path in package.rglob("*")
        if base.is_analyzable(path)
    )


def harness(package: Path = PACKAGE_DIR) -> dict[str, Any]:
    """Version and content of the installed package: the tree-hash pipeline over its files.

    From a clone: `cd src/gauntlet && git ls-files -z | LC_ALL=C sort -z | xargs -0 sha256sum
    | sha256sum`. No install carries a commit; this names one by content.
    """
    measured = tree.fields(tree.digest_listing(package, _package_names(package)))
    return {"version": gauntlet.__version__, "source": measured["tree"], "files": measured["files"]}


def refusal(path: Path, root: Path, cfg: config_mod.Config) -> str | None:
    """Why the record may not go there, or None.

    Inside the root, `.gauntlet/` and every gated path are refused: a protected
    record would enter the tree hash and make every recording run un-skippable,
    and a verified one would read `modified` until the next `gauntlet lock`.
    """
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    for prefix in (*tree.NEVER_HASHED, *tree.gated_paths(cfg, root)):
        if tree.under(relative, prefix):
            return f"--record {path} is under {prefix!r}: never under .gauntlet/ or a gated path"
    return None


def write(path: Path, record: Record) -> None:
    """One object, `indent=2, sort_keys=True`, trailing newline, temp file then replace."""
    tree.write_json(path, asdict(record))


def record(
    path: Path | None,
    results: list[base.GateResult],
    run: tree.Invocation,
    gates: list[str],
    finished: events.Event | None,
    run_id: str,
) -> None:
    """Write the live run's record at the path `--record` named; nothing when it named none."""
    if path is None:
        return
    write(path, from_run(results, run, gates, finished, run_id))
