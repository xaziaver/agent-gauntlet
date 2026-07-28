from __future__ import annotations

import json
from pathlib import Path

from gauntlet import stop


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
