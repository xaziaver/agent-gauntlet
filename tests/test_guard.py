from __future__ import annotations

import json
from pathlib import Path

import pytest

from gauntlet import guard

PATTERNS = ("gauntlet.toml", ".gauntlet/", ".claude/settings.json", "specs/*.json")


def _payload(path: str | None, tool: str = "Edit") -> dict[str, object]:
    tool_input: dict[str, object] = {"old_string": "a", "new_string": "b"}
    if path is not None:
        tool_input["file_path"] = path
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input,
        "cwd": "/somewhere",
        "session_id": "abc123",
    }


def test_parse_payload_accepts_a_hook_object() -> None:
    parsed = guard.parse_payload(json.dumps(_payload("/tmp/a.py")))
    assert parsed["tool_name"] == "Edit"


def test_parse_payload_rejects_non_json() -> None:
    with pytest.raises(guard.PayloadError, match="not valid JSON"):
        guard.parse_payload("not json at all")


def test_parse_payload_rejects_a_json_array() -> None:
    with pytest.raises(guard.PayloadError, match="not a JSON object"):
        guard.parse_payload("[1, 2, 3]")


def test_target_path_reads_file_path() -> None:
    assert guard.target_path(_payload("/tmp/a.py")) == "/tmp/a.py"


def test_target_path_reads_notebook_path() -> None:
    payload = {"tool_input": {"notebook_path": "/tmp/n.ipynb"}}
    assert guard.target_path(payload) == "/tmp/n.ipynb"


def test_target_path_is_none_for_tools_without_a_file() -> None:
    assert guard.target_path({"tool_input": {"command": "ls"}}) is None
    assert guard.target_path({"tool_name": "Bash"}) is None


def test_relative_to_root_handles_absolute_and_relative(tmp_path: Path) -> None:
    absolute = str(tmp_path / "src" / "a.py")
    assert guard.relative_to_root(absolute, tmp_path) == "src/a.py"
    assert guard.relative_to_root("src/a.py", tmp_path) == "src/a.py"


def test_relative_to_root_is_none_outside_the_project(tmp_path: Path) -> None:
    assert guard.relative_to_root("/etc/passwd", tmp_path) is None


@pytest.mark.parametrize(
    ("rel", "pattern"),
    [
        ("gauntlet.toml", "gauntlet.toml"),
        (".gauntlet/coverage.json", ".gauntlet/"),
        (".gauntlet/jscpd/report.json", ".gauntlet/"),
        (".claude/settings.json", ".claude/settings.json"),
        ("specs/approved.json", "specs/*.json"),
    ],
)
def test_matches_protected_paths(rel: str, pattern: str) -> None:
    assert guard.matches(rel, pattern) is True


@pytest.mark.parametrize(
    ("rel", "pattern"),
    [
        ("src/gauntlet/config.py", "gauntlet.toml"),
        ("gauntlet.toml.bak", "gauntlet.toml"),
        (".gauntletnot/x.json", ".gauntlet/"),
        ("specs/notes.md", "specs/*.json"),
    ],
)
def test_does_not_match_unprotected_paths(rel: str, pattern: str) -> None:
    assert guard.matches(rel, pattern) is False


def test_decide_allows_ordinary_source_edits(tmp_path: Path) -> None:
    payload = _payload(str(tmp_path / "src" / "rating.py"))
    assert guard.decide(payload, tmp_path, PATTERNS) is None


def test_decide_blocks_a_threshold_edit(tmp_path: Path) -> None:
    payload = _payload(str(tmp_path / "gauntlet.toml"))
    message = guard.decide(payload, tmp_path, PATTERNS)
    assert message is not None
    assert "gauntlet.toml" in message
    assert "Fix the code" in message


def test_decide_blocks_a_file_inside_a_protected_directory(tmp_path: Path) -> None:
    payload = _payload(str(tmp_path / ".gauntlet" / "coverage.json"))
    assert guard.decide(payload, tmp_path, PATTERNS) is not None


def test_decide_blocks_edits_to_the_hook_config_itself(tmp_path: Path) -> None:
    payload = _payload(str(tmp_path / ".claude" / "settings.json"))
    assert guard.decide(payload, tmp_path, PATTERNS) is not None


def test_decide_allows_tools_that_write_no_file(tmp_path: Path) -> None:
    payload = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}
    assert guard.decide(payload, tmp_path, PATTERNS) is None


def test_decide_allows_paths_outside_the_project(tmp_path: Path) -> None:
    payload = _payload("/etc/hosts")
    assert guard.decide(payload, tmp_path, PATTERNS) is None


def test_decide_with_no_patterns_allows_everything(tmp_path: Path) -> None:
    payload = _payload(str(tmp_path / "gauntlet.toml"))
    assert guard.decide(payload, tmp_path, ()) is None


def test_refusal_gives_the_agent_an_escalation_path() -> None:
    """Without an escape valve, a model facing a wrong threshold can only thrash."""
    message = guard.refusal("gauntlet.toml", "gauntlet.toml")
    assert "let the human decide" in message
