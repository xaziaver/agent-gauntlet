from __future__ import annotations

import json
from pathlib import Path

from gauntlet import scaffold
from gauntlet.scaffold import Action

OTHER_TOOL = {
    "hooks": {
        "PostToolUse": [
            {"matcher": "Edit", "hooks": [{"type": "command", "command": "prettier --write"}]}
        ]
    },
    "permissions": {"allow": ["Bash(git status)"]},
}


def _hooks(text: str) -> dict:
    return json.loads(text)["hooks"]


def test_generated_settings_cover_the_three_events() -> None:
    hooks = _hooks(scaffold.settings_json(None))
    assert set(hooks) == {"PreToolUse", "PostToolUse", "Stop"}


def test_stop_hook_has_no_matcher() -> None:
    """Stop does not support matchers; adding one is silently ignored."""
    stop = _hooks(scaffold.settings_json(None))["Stop"][0]
    assert "matcher" not in stop
    assert stop["hooks"][0]["args"] == ["stop-check"]


def test_fast_hook_uses_changed_scope_and_json() -> None:
    args = _hooks(scaffold.settings_json(None))["PostToolUse"][0]["hooks"][0]["args"]
    assert "--changed" in args
    assert "--json" in args


def test_fast_gates_are_configurable() -> None:
    args = _hooks(scaffold.settings_json(None, fast_gates="static"))["PostToolUse"][0]["hooks"][0][
        "args"
    ]
    assert args[args.index("--gates") + 1] == "static"


def test_handlers_use_exec_form() -> None:
    """args means no shell, so paths and quoting cannot bite."""
    handler = _hooks(scaffold.settings_json(None))["PreToolUse"][0]["hooks"][0]
    assert handler["command"] == "gauntlet"
    assert isinstance(handler["args"], list)


def test_merge_preserves_other_tools_hooks() -> None:
    hooks = _hooks(scaffold.settings_json(json.dumps(OTHER_TOOL)))
    commands = [h["command"] for g in hooks["PostToolUse"] for h in g["hooks"]]
    assert "prettier --write" in commands
    assert "gauntlet" in commands


def test_merge_preserves_unrelated_top_level_keys() -> None:
    merged = json.loads(scaffold.settings_json(json.dumps(OTHER_TOOL)))
    assert merged["permissions"] == {"allow": ["Bash(git status)"]}


def test_rerunning_init_does_not_duplicate_our_handlers() -> None:
    once = scaffold.settings_json(None)
    twice = scaffold.settings_json(once)
    assert json.loads(once) == json.loads(twice)


def test_rerunning_with_new_options_replaces_the_old_handler() -> None:
    first = scaffold.settings_json(None, fast_gates="static,size,complexity")
    second = scaffold.settings_json(first, fast_gates="static")
    handlers = _hooks(second)["PostToolUse"]
    ours = [h for g in handlers for h in g["hooks"] if h["command"] == "gauntlet"]
    assert len(ours) == 1
    assert "static,size,complexity" not in ours[0]["args"]


def test_a_matcher_group_left_empty_is_dropped() -> None:
    only_ours = scaffold.settings_json(None)
    stripped = scaffold._without_ours(_hooks(only_ours)["PreToolUse"])
    assert stripped == []


def test_malformed_settings_are_replaced_rather_than_crashing() -> None:
    assert set(_hooks(scaffold.settings_json("[1, 2, 3]"))) == {"PreToolUse", "PostToolUse", "Stop"}


def test_guidance_block_is_marked_for_idempotent_replacement() -> None:
    block = scaffold.guidance_block()
    assert block.startswith(scaffold.BLOCK_BEGIN)
    assert block.endswith(scaffold.BLOCK_END)


def test_guidance_block_tells_the_agent_to_escalate_not_edit() -> None:
    block = scaffold.guidance_block()
    assert "gauntlet.toml" in block
    assert "let the human decide" in block


def test_upsert_appends_to_an_existing_file() -> None:
    result = scaffold.upsert_block("# My project\n\nNotes.\n", scaffold.guidance_block())
    assert result.startswith("# My project")
    assert scaffold.BLOCK_BEGIN in result


def test_upsert_replaces_only_the_marked_region() -> None:
    first = scaffold.upsert_block("# Project\n", scaffold.guidance_block())
    second = scaffold.upsert_block(first, f"{scaffold.BLOCK_BEGIN}\nnew text\n{scaffold.BLOCK_END}")
    assert "# Project" in second
    assert "new text" in second
    assert second.count(scaffold.BLOCK_BEGIN) == 1
    assert "Quality gates (Gauntlet)" not in second


def test_upsert_is_idempotent() -> None:
    once = scaffold.upsert_block("# Project\n", scaffold.guidance_block())
    assert scaffold.upsert_block(once, scaffold.guidance_block()) == once


def test_plan_for_claude_code(tmp_path: Path) -> None:
    paths = [p for p, _ in scaffold.plan(tmp_path, "claude-code")]
    assert paths == [scaffold.SETTINGS_PATH, scaffold.CLAUDE_MD]


def test_plan_for_generic(tmp_path: Path) -> None:
    paths = [p for p, _ in scaffold.plan(tmp_path, "generic")]
    assert paths == [scaffold.PRECOMMIT_PATH, scaffold.WORKFLOW_PATH]


def test_write_reports_created_then_unchanged(tmp_path: Path) -> None:
    path = Path(".claude") / "settings.json"
    assert scaffold.write(tmp_path, path, "{}\n") is Action.CREATED
    assert scaffold.write(tmp_path, path, "{}\n") is Action.UNCHANGED
    assert scaffold.write(tmp_path, path, '{"a": 1}\n') is Action.UPDATED
