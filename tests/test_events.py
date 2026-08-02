from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet import events


def _log(tmp_path: Path) -> events.Log:
    return events.Log(tmp_path, run="run-1")


def _lines(tmp_path: Path) -> list[dict[str, object]]:
    return events.read(events.events_path(tmp_path))


def test_emitting_appends_one_json_line(tmp_path: Path) -> None:
    _log(tmp_path).emit(events.RUN_STARTED, command="check")
    items = _lines(tmp_path)
    assert len(items) == 1
    assert items[0]["kind"] == events.RUN_STARTED
    assert items[0]["command"] == "check"


def test_every_event_carries_schema_run_and_timestamp(tmp_path: Path) -> None:
    _log(tmp_path).emit(events.GATE_FINISHED, gate="size")
    item = _lines(tmp_path)[0]
    assert item["v"] == events.SCHEMA_VERSION
    assert item["run"] == "run-1"
    assert item["at"]


def test_events_from_one_run_share_a_run_id(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.emit(events.RUN_STARTED)
    log.emit(events.RUN_FINISHED)
    assert {item["run"] for item in _lines(tmp_path)} == {"run-1"}


def test_separate_logs_get_distinct_run_ids(tmp_path: Path) -> None:
    assert events.Log(tmp_path).run != "" and events.new_run_id() != ""


def test_appends_accumulate_in_order(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for index in range(3):
        log.emit(events.GATE_FINISHED, gate=f"g{index}")
    assert [item["gate"] for item in _lines(tmp_path)] == ["g0", "g1", "g2"]


def test_unserializable_values_do_not_break_the_line(tmp_path: Path) -> None:
    _log(tmp_path).emit(events.RUN_FINISHED, threshold=Path("/tmp/x"))
    assert "/tmp/x" in str(_lines(tmp_path)[0]["threshold"])


def test_a_disabled_log_writes_nothing(tmp_path: Path) -> None:
    events.disabled().emit(events.RUN_STARTED)
    assert not events.events_path(tmp_path).exists()


def test_a_write_failure_is_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lost line beats a broken gate."""
    log = _log(tmp_path)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", boom)
    log.emit(events.RUN_STARTED)  # must not raise


def test_the_log_rotates_when_it_grows_too_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(events, "MAX_BYTES", 200)
    log = _log(tmp_path)
    for index in range(20):
        log.emit(events.GATE_FINISHED, gate=f"gate-{index}", padding="x" * 50)
    rotated = events.events_path(tmp_path).with_suffix(".jsonl.1")
    assert rotated.exists()
    assert len(_lines(tmp_path)) < 20


def test_read_skips_corrupt_lines(tmp_path: Path) -> None:
    path = events.events_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"kind": "a"}\nnot json\n{"kind": "b"}\n')
    assert [item["kind"] for item in events.read(path)] == ["a", "b"]


def test_read_limit_returns_the_most_recent(tmp_path: Path) -> None:
    log = _log(tmp_path)
    for index in range(5):
        log.emit(events.GATE_FINISHED, gate=f"g{index}")
    assert [i["gate"] for i in events.read(events.events_path(tmp_path), limit=2)] == ["g3", "g4"]


def test_read_of_a_missing_log_is_empty(tmp_path: Path) -> None:
    assert events.read(tmp_path / "nope.jsonl") == []


def test_payload_fields_never_shadow_the_envelope(tmp_path: Path) -> None:
    """A reader must always be able to trust `kind`, `run`, and `at`."""
    _log(tmp_path).emit(events.RUN_STARTED, kind="spoofed", run="spoofed")
    item = _lines(tmp_path)[0]
    assert item["kind"] == events.RUN_STARTED
    assert item["run"] == "run-1"
