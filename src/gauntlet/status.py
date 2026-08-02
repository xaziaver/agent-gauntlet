"""Project status: gates, pending approvals, recent activity.

Composition only — no new measurement. The gates already answer "is this
acceptable", the ledger answers "what have I approved", and the event log
answers "what has been happening". This assembles them into the view a person
managing an agent actually wants, and into one JSON object a dashboard can
render without reaching into internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gauntlet import config as config_mod
from gauntlet import events, locking, registry, specs
from gauntlet.gates.base import GateResult

MAX_RECENT = 8
PENDING_STATUSES = (registry.Status.UNAPPROVED, registry.Status.MODIFIED, registry.Status.MISSING)

ACTION_FOR = {
    locking.CONFIG_NAMESPACE: "gauntlet lock",
    specs.SPEC_NAMESPACE: "gauntlet spec approve {subject}",
}
DEFAULT_ACTION = "gauntlet review"


@dataclass(frozen=True)
class Pending:
    """One thing a human has to decide."""

    namespace: str
    subject: str
    status: str

    @property
    def action(self) -> str:
        template = ACTION_FOR.get(self.namespace, DEFAULT_ACTION)
        return template.format(subject=self.subject)

    def to_dict(self) -> dict[str, str]:
        return {
            "namespace": self.namespace,
            "subject": self.subject,
            "status": self.status,
            "action": self.action,
        }


@dataclass(frozen=True)
class Status:
    root: Path
    gates: list[GateResult] = field(default_factory=list)
    pending: list[Pending] = field(default_factory=list)
    recent: list[dict[str, Any]] = field(default_factory=list)
    locked: bool = False

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "locked": self.locked,
            "gates": [
                {"gate": g.gate, "passed": g.passed, "actual": g.actual, "error": g.error}
                for g in self.gates
            ],
            "pending": [p.to_dict() for p in self.pending],
            "recent": self.recent,
        }


def _findings_to_pending(namespace: str, findings: list[registry.Finding]) -> list[Pending]:
    return [
        Pending(namespace=namespace, subject=registry.bare(f.key), status=f.status.value)
        for f in findings
        if f.status in PENDING_STATUSES
    ]


def _config_pending(
    root: Path, cfg: config_mod.Config, approved: registry.Registry
) -> list[Pending]:
    findings = locking.verify_config(root, cfg.verified_paths, approved)
    return _findings_to_pending(locking.CONFIG_NAMESPACE, findings)


def _spec_pending(root: Path, cfg: config_mod.Config, approved: registry.Registry) -> list[Pending]:
    features_dir = str(cfg.gates.get("acceptance", {}).get("features", "features/"))
    found = specs.discover(root, features_dir)
    if not found:
        return []
    return _findings_to_pending(specs.SPEC_NAMESPACE, specs.verify(root, found, approved))


def pending(root: Path, cfg: config_mod.Config) -> list[Pending]:
    """Approvals waiting on a human, without running any gate.

    Mutants are excluded on purpose: knowing whether one survives requires
    actually running the mutation, which is not a cheap status query.
    """
    approved = registry.load(locking.lock_path(root))
    return [*_config_pending(root, cfg, approved), *_spec_pending(root, cfg, approved)]


def collect(root: Path, cfg: config_mod.Config, gates: list[GateResult] | None = None) -> Status:
    return Status(
        root=root,
        gates=gates or [],
        pending=pending(root, cfg),
        recent=events.read(events.events_path(root), MAX_RECENT),
        locked=locking.lock_path(root).exists(),
    )
