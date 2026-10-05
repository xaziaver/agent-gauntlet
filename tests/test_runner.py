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


class _Fixed:
    """A gate that returns the result it was given."""

    def __init__(self, result: base.GateResult) -> None:
        self.name = result.gate
        self.result = result

    def run(self, ctx: base.GateContext, config: dict[str, Any]) -> base.GateResult:
        return self.result


def test_the_runner_emits_counts_only_on_a_gate_that_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    counted = {"features/a.feature": {"killed": 2, "total": 4}}
    for result in (
        base.GateResult(gate="plain", passed=True, threshold=1, actual=1),
        base.GateResult(gate="counting", passed=True, threshold=1, actual=1, counts=counted),
    ):
        monkeypatch.setitem(runner.REGISTRY, result.gate, _Fixed(result))
    gates: dict[str, Any] = {"plain": {}, "counting": {}}
    cfg = config_mod.Config("python", tmp_path / "src", tmp_path / "tests", gates, {}, {})
    ctx = base.GateContext(project_root=tmp_path, src=tmp_path / "src", tests=tmp_path / "tests")
    runner.run_gates(ctx, cfg, ["plain", "counting"], False, log=events.Log(tmp_path, "r1"))
    lines = (tmp_path / ".gauntlet" / "events.jsonl").read_text().splitlines()
    plain, counting = [json.loads(line) for line in lines]
    envelope = {"v", "at", "run", "kind"}
    six = {"gate", "passed", "actual", "duration", "diagnostics", "error"}
    assert set(plain) - envelope == six
    assert set(counting) - envelope == six | {"counts"}
    assert counting["counts"] == counted
