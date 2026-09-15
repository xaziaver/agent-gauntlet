"""The gated tree's hash, and the last-green record `stop-check` skips on.

A run measures a tree. Recording which tree lets the next `stop-check` answer
"are you done" with an earlier run as the evidence, when nothing any gate reads
has changed since. The hash is the shell pipeline ClaimGate's wrapper used, so
anyone can recompute it from a clone with no Gauntlet install:

    git ls-files -z -c -o --exclude-standard -- <paths> | LC_ALL=C sort -z \\
        | xargs -0 sha256sum | sha256sum

Tracked and untracked-not-ignored files both enter, so a clone reproduces a
recorded value only for a tree that had no untracked gated files; the `files`
count beside the hash is the first thing to compare when it does not. A path is
part of the line, so a content-identical rename moves the hash. A file git lists
that is missing on disk (a deleted tracked file), git absent, or git failing all
mean no hash: the run is recorded with `tree: null` and never skipped.

The record, `.gauntlet/last-green.json`, is a skip cache: gate-writable and
unverified, never evidence of anything. A run is.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gauntlet import config as config_mod
from gauntlet import events, report
from gauntlet.gates import base, boundary
from gauntlet.gates.base import run_cmd

RECORD_FILE = Path(".gauntlet") / "last-green.json"
SKIP_HELP = "Skip every gate when the gated tree matches the last wholly green run"

# The acceptance gate's defaults, restated: acceptance.run() reads them inline.
ACCEPTANCE_PATH_DEFAULTS = {"features": "features/", "steps": "tests/steps"}
BOUNDARY_PATH_DEFAULTS = {"steps": boundary.DEFAULT_STEPS, "api": boundary.DEFAULT_API}

# Gate-writable and unverified: hashing it would move the hash on every run.
NEVER_HASHED = (".gauntlet", events.EVENTS_FILE.parent.as_posix())


@dataclass(frozen=True)
class TreeHash:
    tree: str
    files: int


@dataclass(frozen=True)
class GreenRecord:
    """What the last wholly green run measured, and which run it was."""

    tree: str
    files: int
    run: str
    at: str
    command: str
    gates: list[str]


@dataclass(frozen=True)
class Invocation:
    """One run's shape: where, what, which command, which tree, whole or `--changed`."""

    root: Path
    cfg: config_mod.Config
    command: str
    measured: TreeHash | None
    changed: bool = False


def _gate_paths(cfg: config_mod.Config, gate: str, defaults: dict[str, str]) -> list[str]:
    """A gate's configured paths, its own defaults filling the gaps; none if it is off."""
    table = cfg.gates.get(gate)
    if table is None:
        return []
    return [str(table.get(key, default)) for key, default in defaults.items()]


def under(path: str, prefix: str) -> bool:
    """Is the POSIX-relative path the prefix itself or below it?"""
    return path == prefix or path.startswith(prefix + "/")


def gated_paths(cfg: config_mod.Config, root: Path) -> list[str]:
    """Every path a gate reads, relative to the root, deduplicated, `.gauntlet/` removed."""
    candidates = [
        os.path.relpath(cfg.src, root),
        os.path.relpath(cfg.tests, root),
        *_gate_paths(cfg, "acceptance", ACCEPTANCE_PATH_DEFAULTS),
        *_gate_paths(cfg, "boundary", BOUNDARY_PATH_DEFAULTS),
        *cfg.protected_paths,
        *cfg.verified_paths,
    ]
    kept: list[str] = []
    for candidate in candidates:
        path = Path(candidate).as_posix()
        if path in kept or any(under(path, prefix) for prefix in NEVER_HASHED):
            continue
        kept.append(path)
    return kept


def _listing(root: Path, paths: list[str]) -> list[bytes] | None:
    """git's file list for the paths, bytewise sorted; None when git cannot say."""
    if not paths:
        return None
    args = ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard", "--", *paths]
    try:
        proc = run_cmd(args, cwd=root)
    except UnicodeDecodeError:  # a file name git cannot say in text: never raise in a hook
        return None
    if proc.returncode != 0:
        return None
    return sorted(name.encode("utf-8") for name in proc.stdout.split("\0") if name)


def digest_listing(root: Path, names: list[bytes]) -> TreeHash | None:
    """sha256 over one `<sha256 of content>  <path>\\n` line per name; None if one is unreadable."""
    digest = hashlib.sha256()
    for name in names:
        try:
            content = (root / os.fsdecode(name)).read_bytes()
        except OSError:
            return None
        line = hashlib.sha256(content).hexdigest().encode("ascii") + b"  " + name + b"\n"
        digest.update(line)
    return TreeHash(tree=digest.hexdigest(), files=len(names))


def hash_tree(root: Path, paths: list[str]) -> TreeHash | None:
    """The digest over git's listing of the paths; None when git cannot say."""
    names = _listing(root, paths)
    if names is None:
        return None
    return digest_listing(root, names)


def measure(root: Path, cfg: config_mod.Config) -> TreeHash | None:
    return hash_tree(root, gated_paths(cfg, root))


def fields(measured: TreeHash | None) -> dict[str, Any]:
    """The two `run.finished` fields; both null when the tree could not be hashed."""
    if measured is None:
        return {"tree": None, "files": None}
    return {"tree": measured.tree, "files": measured.files}


def finished_fields(run: Invocation, results: list[base.GateResult]) -> dict[str, Any]:
    """The `run.finished` payload for one run."""
    return {
        "command": run.command,
        "passed": report.passed(results),
        "failed": [r.gate for r in results if not r.passed],
        **fields(run.measured),
    }


def reused_fields(record: GreenRecord) -> dict[str, Any]:
    """The `run.reused` payload: which tree, and which run is the evidence."""
    return {
        "command": "stop-check",
        "tree": record.tree,
        "files": record.files,
        "reused_run": record.run,
        "reused_at": record.at,
    }


def skip_line(record: GreenRecord) -> str:
    """The wrapper's wording, so a reader of either log sees one shape."""
    return (
        "gauntlet stop-check skipped: gated tree unchanged since green run "
        f"{record.run}, {record.at}"
    )


def wholly_green(cfg: config_mod.Config, results: list[base.GateResult], changed: bool) -> bool:
    """Every enabled gate ran, over the whole tree, and every one passed.

    Decided from this process's own results and selection, never from the log.
    """
    ran = [r.gate for r in results]
    return not changed and ran == cfg.enabled_gates and report.passed(results)


def record_path(root: Path) -> Path:
    return root / RECORD_FILE


def read_record(root: Path) -> GreenRecord | None:
    """The record, or None when it is missing or not the six fields it should be."""
    try:
        raw = json.loads(record_path(root).read_text(encoding="utf-8"))
        return GreenRecord(
            tree=str(raw["tree"]),
            files=int(raw["files"]),
            run=str(raw["run"]),
            at=str(raw["at"]),
            command=str(raw["command"]),
            gates=[str(gate) for gate in raw["gates"]],
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Temp file then replace: a reader never sees half a record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def write_record(root: Path, record: GreenRecord) -> None:
    write_json(record_path(root), asdict(record))


def remember(
    run: Invocation, results: list[base.GateResult], finished: events.Event | None
) -> None:
    """Write the record after a wholly green, hashed, logged run; otherwise leave it alone."""
    if finished is None or run.measured is None:
        return
    if not wholly_green(run.cfg, results, run.changed):
        return
    write_record(
        run.root,
        GreenRecord(
            tree=run.measured.tree,
            files=run.measured.files,
            run=finished.run,
            at=finished.at,
            command=run.command,
            gates=run.cfg.enabled_gates,
        ),
    )


def reusable(run: Invocation) -> GreenRecord | None:
    """The record, when it names this run's exact tree and the gates enabled now."""
    record = read_record(run.root)
    if run.measured is None or record is None:
        return None
    if record.tree != run.measured.tree or record.gates != run.cfg.enabled_gates:
        return None
    return record
