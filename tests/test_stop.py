from __future__ import annotations

import json
from pathlib import Path

import pytest

from gauntlet import registry, stop
from gauntlet.gates.base import Diagnostic, GateResult


def test_session_id_reads_the_payload() -> None:
    assert stop.session_id({"session_id": "abc123"}) == "abc123"


def test_session_id_falls_back_for_a_missing_id() -> None:
    assert stop.session_id({}) == stop.UNKNOWN_SESSION


def test_record_failure_increments_without_mutating() -> None:
    original = {"a": 1}
    state, count = stop.record_failure(original, "a")
    assert original == {"a": 1}
    assert (state["a"], count) == (2, 2)


def test_record_failure_starts_a_new_session_at_one() -> None:
    _, count = stop.record_failure({}, "new")
    assert count == 1


def test_sessions_are_counted_separately() -> None:
    state, _ = stop.record_failure({"a": 2}, "b")
    assert state == {"a": 2, "b": 1}


def test_clear_session_forgets_only_that_session() -> None:
    assert stop.clear_session({"a": 3, "b": 1}, "a") == {"b": 1}


def test_should_escalate_only_at_the_cap() -> None:
    assert stop.should_escalate(2, 3) is False
    assert stop.should_escalate(3, 3) is True
    assert stop.should_escalate(4, 3) is True


def test_escalation_message_names_the_count_and_carries_the_report() -> None:
    message = stop.escalation_message(3, "✗ complexity ...")
    assert "3 attempts" in message
    assert "✗ complexity" in message


def test_attempts_round_trip(tmp_path: Path) -> None:
    path = stop.attempts_path(tmp_path)
    stop.save_attempts({"a": 2}, path)
    assert stop.load_attempts(path) == {"a": 2}


def test_missing_attempts_file_is_empty(tmp_path: Path) -> None:
    assert stop.load_attempts(tmp_path / "nope.json") == {}


def test_corrupt_attempts_state_resets_rather_than_crashing(tmp_path: Path) -> None:
    """Losing the count is harmless; crashing a Stop hook is not."""
    path = tmp_path / "attempts.json"
    path.write_text("{not json")
    assert stop.load_attempts(path) == {}


def test_non_integer_counts_are_discarded(tmp_path: Path) -> None:
    path = tmp_path / "attempts.json"
    path.write_text(json.dumps({"a": "three", "b": 2}))
    assert stop.load_attempts(path) == {"b": 2}


def _red(*diagnostics: Diagnostic, error: str | None = None) -> GateResult:
    return GateResult(
        gate="acceptance",
        passed=False,
        threshold="t",
        actual="a",
        diagnostics=list(diagnostics),
        error=error,
    )


def _finding(symbol: str) -> Diagnostic:
    return Diagnostic(file="features/a.feature", message="m", symbol=symbol)


GREEN = GateResult(gate="size", passed=True, threshold="t", actual="a")


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        pytest.param(
            [GREEN, _red(_finding("unapproved"), _finding("modified"), _finding("missing"))],
            True,
            id="all approval symbols",
        ),
        pytest.param(
            [_red(_finding("unapproved"), _finding("Quarters"))], False, id="one other symbol"
        ),
        pytest.param([_red(error="pytest exited 127")], False, id="error set"),
        pytest.param(
            [_red(_finding("unapproved"), error="tool crashed")],
            False,
            id="error set beside approval findings",
        ),
        pytest.param([_red()], False, id="no diagnostics"),
        pytest.param([GREEN], False, id="nothing failed"),
        pytest.param([], False, id="nothing ran"),
        pytest.param(
            [_red(_finding("unapproved")), _red(_finding("big"))],
            False,
            id="two gates, one agent-actionable",
        ),
    ],
)
def test_human_blocked_is_true_only_for_approval_findings(
    results: list[GateResult], expected: bool
) -> None:
    """Every failure must be one only a human clears — an approval finding, or an error
    that names the ledger first; anything else, a pytest exit or a crashed tool included,
    is the agent's."""
    assert stop.human_blocked(results) is expected


def test_a_gate_whose_error_names_the_ledger_is_human_blocked(tmp_path: Path) -> None:
    """The error string is the registry's own, raised through `load` on a version-1
    file, never typed: the property this rests on is that every refusal names the
    ledger first."""
    lock = tmp_path / "gauntlet.lock.json"
    lock.write_text('{"version": 1, "entries": {}}\n')
    with pytest.raises(registry.RegistryError) as raised:
        registry.load(lock)
    error = str(raised.value)
    assert error.split()[0] == str(lock)
    assert stop.human_blocked([GREEN, _red(error=error)]) is True
    assert stop.human_blocked([_red(error=error), _red(_finding("unapproved"))]) is True
    assert stop.human_blocked([_red(error=error), _red(_finding("big"))]) is False


@pytest.mark.parametrize(
    "error",
    [
        "pytest exited 127: could not run '/nowhere/python': No such file or directory",
        "tool crashed reading gauntlet.lock.json",
        "the ledger /p/gauntlet.lock.json is fine; something else is not",
        "",
    ],
)
def test_an_error_that_does_not_name_the_ledger_is_the_agent_s(error: str) -> None:
    """Only the first token counts: a mention of the ledger later in the text is not a
    refusal of it, and a pytest exit names pytest or a path."""
    assert stop.human_blocked([_red(error=error)]) is False


def test_blocked_message_names_no_command() -> None:
    """One command for every cause was the defect: a spec, a mutant and a ledger refusal
    each carry their own remedy in the report, so the preamble names none."""
    message = stop.blocked_message("✗ acceptance ...")
    preamble, _, carried = message.partition("\n")
    assert preamble.startswith(
        "Gauntlet is blocked on a human: the failures below need a human's action"
    )
    assert "gauntlet" not in preamble
    assert preamble.endswith("Nothing here is for the agent.")
    assert carried == "✗ acceptance ..."
