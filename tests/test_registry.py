from __future__ import annotations

import json
from pathlib import Path

import pytest

from gauntlet import registry
from gauntlet.registry import Status

CONTENT = b"line = 95\nbranch = 90\n"
OTHER = b"line = 50\nbranch = 40\n"


def _approved(key: str = "gauntlet.toml", content: bytes = CONTENT) -> registry.Registry:
    return registry.approve(registry.Registry(), key, content, when="2026-07-28T00:00:00+00:00")


def test_digest_is_stable_and_prefixed() -> None:
    assert registry.digest(CONTENT) == registry.digest(CONTENT)
    assert registry.digest(CONTENT).startswith("sha256:")


def test_digest_differs_for_different_content() -> None:
    assert registry.digest(CONTENT) != registry.digest(OTHER)


def test_digest_normalizes_line_endings() -> None:
    """A CRLF flip is not a change a human approved."""
    assert registry.digest(b"a\r\nb\r\n") == registry.digest(b"a\nb\n")


def test_approve_returns_a_new_registry_without_mutating() -> None:
    original = registry.Registry()
    updated = registry.approve(original, "k", CONTENT)
    assert original.entries == {}
    assert updated.entries["k"].digest == registry.digest(CONTENT)


def test_approve_replaces_an_existing_entry() -> None:
    first = _approved()
    second = registry.approve(first, "gauntlet.toml", OTHER)
    assert second.entries["gauntlet.toml"].digest == registry.digest(OTHER)
    assert len(second.entries) == 1


def test_revoke_removes_only_that_key() -> None:
    reg = registry.approve(_approved(), "other.toml", OTHER)
    assert set(registry.revoke(reg, "other.toml").entries) == {"gauntlet.toml"}


def test_verify_unchanged() -> None:
    finding = registry.verify(_approved(), "gauntlet.toml", CONTENT)
    assert finding.status is Status.UNCHANGED


def test_verify_modified_reports_both_digests() -> None:
    finding = registry.verify(_approved(), "gauntlet.toml", OTHER)
    assert finding.status is Status.MODIFIED
    assert finding.expected == registry.digest(CONTENT)
    assert finding.actual == registry.digest(OTHER)


def test_verify_missing_when_an_approved_subject_is_gone() -> None:
    finding = registry.verify(_approved(), "gauntlet.toml", None)
    assert finding.status is Status.MISSING


def test_verify_unapproved_stays_distinct_from_modified() -> None:
    """Conflating these is how approval degrades into a rubber stamp."""
    finding = registry.verify(registry.Registry(), "new.feature", CONTENT)
    assert finding.status is Status.UNAPPROVED
    assert finding.expected is None


def test_verify_all_includes_approved_keys_the_subjects_omit() -> None:
    findings = registry.verify_all(_approved(), {"other.toml": OTHER})
    statuses = {f.key: f.status for f in findings}
    assert statuses == {"gauntlet.toml": Status.MISSING, "other.toml": Status.UNAPPROVED}


def test_verify_all_is_sorted_for_stable_output() -> None:
    findings = registry.verify_all(registry.Registry(), {"b": CONTENT, "a": CONTENT})
    assert [f.key for f in findings] == ["a", "b"]


def test_load_of_a_missing_file_is_an_empty_registry(tmp_path: Path) -> None:
    assert registry.load(tmp_path / "nope.json").entries == {}


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "gauntlet.lock.json"
    registry.save(_approved(), path)
    assert registry.load(path).entries["gauntlet.toml"].digest == registry.digest(CONTENT)


def test_save_is_deterministic_and_diff_friendly(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    reg = registry.approve(_approved("z.toml"), "a.toml", OTHER, when="2026-01-01T00:00:00+00:00")
    registry.save(reg, path)
    text = path.read_text()
    assert text.endswith("\n")
    assert text.index('"a.toml"') < text.index('"z.toml"')


def test_load_rejects_a_wrong_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"version": 99, "entries": {}}))
    with pytest.raises(registry.RegistryError, match="schema version"):
        registry.load(path)


def test_load_rejects_a_malformed_entries_table(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"version": 1, "entries": []}))
    with pytest.raises(registry.RegistryError, match="entries table"):
        registry.load(path)


def test_load_rejects_an_entry_without_a_digest(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"version": 1, "entries": {"k": {"approved_at": "now"}}}))
    with pytest.raises(registry.RegistryError, match="malformed"):
        registry.load(path)


def test_load_rejects_unparsable_json(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    path.write_text("{not json")
    with pytest.raises(registry.RegistryError, match="unreadable"):
        registry.load(path)


def test_describe_modified_offers_revert_or_reapproval() -> None:
    message = registry.describe(registry.Finding("gauntlet.toml", Status.MODIFIED))
    assert "revert" in message
    assert "gauntlet lock" in message


def test_describe_uses_the_caller_s_noun() -> None:
    message = registry.describe(registry.Finding("rating.feature", Status.MODIFIED), noun="spec")
    assert "This spec is the human's artifact" in message


def test_verify_absent_and_unapproved_is_not_a_finding() -> None:
    """A default verified path that a project does not have is normal, not a violation."""
    finding = registry.verify(registry.Registry(), "pyproject.toml", None)
    assert finding.status is Status.ABSENT
    assert finding.expected is None
    assert finding.actual is None
