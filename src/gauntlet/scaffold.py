"""Generates agent and CI integration files.

Everything here is pure: functions return the text or structure to write, and the
CLI decides what lands on disk. Generation is idempotent — re-running init must
update Gauntlet's own entries and leave everything else in the file alone.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from gauntlet.templates import (
    CONFTEST,
    GAUNTLET_TOML_TEMPLATE,
    GITHUB_WORKFLOW,
    GUIDANCE_BODY,
    PACKAGE_INIT,
    PLACEHOLDER_MODULE,
    PLACEHOLDER_TEST,
    PRECOMMIT_CONFIG,
)

COMMAND = "gauntlet"
CONFIG_PATH = Path("gauntlet.toml")

# Exact-match tool list: only letters and `|`, so Claude Code compares it as a
# set of exact names rather than a regular expression.
FILE_TOOLS = "Edit|Write|MultiEdit|NotebookEdit"

FAST_GATES = "static,size,complexity"

SETTINGS_PATH = Path(".claude") / "settings.json"
CLAUDE_MD = Path("CLAUDE.md")
PRECOMMIT_PATH = Path(".pre-commit-config.yaml")
WORKFLOW_PATH = Path(".github") / "workflows" / "gauntlet.yml"
CONFTEST_PATH = Path("conftest.py")

BLOCK_BEGIN = "<!-- gauntlet:begin -->"
BLOCK_END = "<!-- gauntlet:end -->"


class Action(Enum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


def package_name(root: Path) -> str:
    """A valid Python package name derived from the project directory."""
    cleaned = re.sub(r"[^0-9a-zA-Z_]", "_", root.name.lower()).strip("_")
    if not cleaned:
        return "app"
    return f"pkg_{cleaned}" if cleaned[0].isdigit() else cleaned


def baseline_files(root: Path) -> list[tuple[Path, str]]:
    """A minimal green baseline: a package, one module, one test, one conftest.

    Without these the first `gauntlet check` on a new project fails three gates,
    none of which names the actual cause — an empty source tree. A new project
    should be green by construction.
    """
    package = package_name(root)
    return [
        (CONFTEST_PATH, CONFTEST),
        (Path("src") / package / "__init__.py", PACKAGE_INIT.format(package=package)),
        (Path("src") / package / "placeholder.py", PLACEHOLDER_MODULE),
        (Path("tests") / "test_placeholder.py", PLACEHOLDER_TEST.format(package=package)),
    ]


def _handler(args: list[str], timeout: int, status: str | None = None) -> dict[str, Any]:
    """Exec form: `args` means no shell, so paths and quoting cannot bite."""
    handler: dict[str, Any] = {
        "type": "command",
        "command": COMMAND,
        "args": args,
        "timeout": timeout,
    }
    if status:
        handler["statusMessage"] = status
    return handler


def _pre_tool_use() -> list[dict[str, Any]]:
    """Blocks edits to protected paths before they happen."""
    return [{"matcher": FILE_TOOLS, "hooks": [_handler(["guard"], 10)]}]


def _post_tool_use(fast_gates: str) -> list[dict[str, Any]]:
    """Cannot block — the edit already happened — but stderr reaches the model."""
    args = ["check", "--gates", fast_gates, "--changed", "--json"]
    return [{"matcher": FILE_TOOLS, "hooks": [_handler(args, 60, "Gauntlet: fast gates")]}]


def _stop() -> list[dict[str, Any]]:
    """The real gate. No matcher: Stop does not support one."""
    return [{"hooks": [_handler(["stop-check"], 600, "Gauntlet: full run")]}]


def claude_hooks(fast_gates: str = FAST_GATES) -> dict[str, Any]:
    """The three hook events Gauntlet owns."""
    return {
        "PreToolUse": _pre_tool_use(),
        "PostToolUse": _post_tool_use(fast_gates),
        "Stop": _stop(),
    }


def _is_ours(handler: Any) -> bool:
    return isinstance(handler, dict) and handler.get("command") == COMMAND


def _without_ours(groups: list[Any]) -> list[Any]:
    """Drop Gauntlet handlers, and any matcher group left empty by their removal."""
    kept: list[Any] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        handlers = [h for h in group.get("hooks", []) if not _is_ours(h)]
        if handlers:
            kept.append({**group, "hooks": handlers})
    return kept


def merge_settings(existing: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    """Splice Gauntlet's hooks into a settings file without disturbing anything else.

    Identity is the command name, so re-running init replaces Gauntlet's own
    handlers rather than appending duplicates, and other tools' hooks survive.
    """
    merged = dict(existing)
    hooks = dict(merged.get("hooks", {}))
    for event, groups in generated.items():
        hooks[event] = _without_ours(hooks.get(event, [])) + groups
    merged["hooks"] = hooks
    return merged


def settings_json(existing_text: str | None, fast_gates: str = FAST_GATES) -> str:
    existing = json.loads(existing_text) if existing_text else {}
    if not isinstance(existing, dict):
        existing = {}
    return json.dumps(merge_settings(existing, claude_hooks(fast_gates)), indent=2) + "\n"


def guidance_block() -> str:
    """Advisory context for CLAUDE.md. Context, never enforcement.

    Worth including even though it decays: capable models read ambient signals and
    raise their own bar. The gates remain the only thing relied upon.
    """
    return f"{BLOCK_BEGIN}\n{GUIDANCE_BODY}{BLOCK_END}"


def upsert_block(existing_text: str | None, block: str) -> str:
    """Replace the marked block if present, otherwise append it."""
    if not existing_text:
        return block + "\n"
    start = existing_text.find(BLOCK_BEGIN)
    end = existing_text.find(BLOCK_END)
    if start == -1 or end == -1 or end < start:
        return existing_text.rstrip("\n") + "\n\n" + block + "\n"
    return existing_text[:start] + block + existing_text[end + len(BLOCK_END) :]


def _agent_files(agent: str, fast_gates: str, read: Any) -> list[tuple[Path, str]]:
    if agent == "claude-code":
        return [
            (SETTINGS_PATH, settings_json(read(SETTINGS_PATH), fast_gates)),
            (CLAUDE_MD, upsert_block(read(CLAUDE_MD), guidance_block())),
        ]
    return [(PRECOMMIT_PATH, PRECOMMIT_CONFIG), (WORKFLOW_PATH, GITHUB_WORKFLOW)]


def plan(root: Path, agent: str, fast_gates: str = FAST_GATES) -> list[tuple[Path, str]]:
    """(path, new content) for each file this agent target needs.

    A starter gauntlet.toml and a green baseline are included only when no config
    exists — plan never overwrites the human's thresholds, and an existing project
    already has its own layout.
    """

    def read(path: Path) -> str | None:
        full = root / path
        return full.read_text(encoding="utf-8") if full.is_file() else None

    entries: list[tuple[Path, str]] = []
    if read(CONFIG_PATH) is None:
        entries.append((CONFIG_PATH, GAUNTLET_TOML_TEMPLATE))
        entries.extend((p, c) for p, c in baseline_files(root) if read(p) is None)
    entries.extend(_agent_files(agent, fast_gates, read))
    return entries


def write(root: Path, path: Path, content: str) -> Action:
    full = root / path
    if full.is_file() and full.read_text(encoding="utf-8") == content:
        return Action.UNCHANGED
    action = Action.UPDATED if full.exists() else Action.CREATED
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return action
