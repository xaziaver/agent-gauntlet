"""The runner's contract with a gate that a signal interrupts: log it, then die."""

from __future__ import annotations

import json
import signal
from pathlib import Path
from typing import Any

import pytest

from gauntlet import config as config_mod
from gauntlet import events, runner
from gauntlet.gates import base


class _Raising:
    """A gate that a signal lands in."""

    name = "raising"

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def run(self, ctx: base.GateContext, config: dict[str, Any]) -> base.GateResult:
        raise self.exc


def _run(root: Path, monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> list[dict[str, Any]]:
    died: list[int] = []

    def die(self: base.Interrupted) -> None:
        died.append(self.signum)
        raise SystemExit(128 + self.signum)

    monkeypatch.setattr(base.Interrupted, "die", die)
    monkeypatch.setitem(runner.REGISTRY, "raising", _Raising(exc))
    cfg = config_mod.Config("python", root / "src", root / "tests", {"raising": {}}, {}, {})
    ctx = base.GateContext(project_root=root, src=root / "src", tests=root / "tests")
    with pytest.raises(SystemExit) as ended:
        runner.run_gates(ctx, cfg, ["raising"], fail_fast=False, log=events.Log(root, "r1"))
    assert ended.value.code == 128 + died[0]
    lines = (root / ".gauntlet" / "events.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def test_an_interrupted_gate_writes_run_interrupted_then_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _run(tmp_path, monkeypatch, base.Interrupted(signal.SIGTERM))
    assert log[-1]["kind"] == "run.interrupted"
    assert log[-1]["gate"] == "raising"
    assert log[-1]["signal"] == "SIGTERM"
    assert log[-1]["run"] == "r1"
    assert not [line for line in log if line["kind"] == "gate.finished"]


def test_a_keyboard_interrupt_in_a_gate_is_logged_as_sigint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = _run(tmp_path, monkeypatch, KeyboardInterrupt())
    assert log[-1]["kind"] == "run.interrupted"
    assert log[-1]["signal"] == "SIGINT"
