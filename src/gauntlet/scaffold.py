"""Generates agent and CI integration files.

Everything here is pure: functions return the text or structure to write, and the
CLI decides what lands on disk. Generation is idempotent — re-running init must
update Gauntlet's own entries and leave everything else in the file alone.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

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

BLOCK_BEGIN = "<!-- gauntlet:begin -->"
BLOCK_END = "<!-- gauntlet:end -->"

PRECOMMIT_CONFIG = """repos:
  - repo: local
    hooks:
      - id: gauntlet
        name: gauntlet
        entry: gauntlet check --changed
        language: system
        pass_filenames: false
        always_run: true
"""

GITHUB_WORKFLOW = """name: gauntlet

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  gauntlet:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Install uv
        uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true

      - name: Install the project
        run: uv sync --dev

      - name: Run the gauntlet
        run: uv run gauntlet check --json

      - name: Upload gauntlet report
        if: always()
        uses: actions/upload-artifact@v5
        with:
          name: gauntlet-report
          path: .gauntlet/
          if-no-files-found: ignore
"""

GAUNTLET_TOML_TEMPLATE = """\
# Gauntlet quality gates. This file is the human's artifact: edit it, then run
# `gauntlet lock` to approve it. Agents are blocked from changing it.

[project]
language = "python"
src = "src/"
tests = "tests/"

[output]
max_diagnostics_per_gate = 10

[gates.protect]
# require_lock = true   # enable once you have run `gauntlet lock`

[gates.static]

[gates.size]
max_function_lines = 25
max_module_lines = 300

[gates.complexity]
max = 6

[gates.tests]

[gates.coverage]
line = 90
branch = 80

[gates.crap]
max = 15

# Requires jscpd (npm install -g jscpd); enable when installed.
# [gates.duplication]
# max_duplicate_blocks = 0
"""


class Action(Enum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


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
    return f"""{BLOCK_BEGIN}
## Quality gates (Gauntlet)

This project is gated. Implementation code is yours; thresholds and approvals are
the human's.

- Run `gauntlet check` yourself before you say you are done. Do not wait for the
  Stop hook to tell you.
- Gate failures come back as JSON with a file, a symbol, a line, and a remedy.
  Act on the remedy rather than guessing.
- Never edit `gauntlet.toml`, `gauntlet.lock.json`, `.claude/settings.json`, or
  anything under `.gauntlet/`. Weakening a threshold is not a way to pass a gate.
  If you believe a threshold is genuinely wrong, say so and let the human decide.
- Write tests that would fail if the behavior were wrong. Coverage of code that
  asserts nothing is worthless and later gates are designed to catch it.
- Prefer extracting functions over suppressing a finding. `# noqa` and
  `# type: ignore` are last resorts, not shortcuts.
{BLOCK_END}"""


def upsert_block(existing_text: str | None, block: str) -> str:
    """Replace the marked block if present, otherwise append it."""
    if not existing_text:
        return block + "\n"
    start = existing_text.find(BLOCK_BEGIN)
    end = existing_text.find(BLOCK_END)
    if start == -1 or end == -1 or end < start:
        return existing_text.rstrip("\n") + "\n\n" + block + "\n"
    return existing_text[:start] + block + existing_text[end + len(BLOCK_END) :]


def plan(root: Path, agent: str, fast_gates: str = FAST_GATES) -> list[tuple[Path, str]]:
    """(path, new content) for each file this agent target needs.

    A starter gauntlet.toml is included only when none exists — plan never
    overwrites the human's thresholds.
    """

    def read(path: Path) -> str | None:
        full = root / path
        return full.read_text(encoding="utf-8") if full.is_file() else None

    entries: list[tuple[Path, str]] = []
    if read(CONFIG_PATH) is None:
        entries.append((CONFIG_PATH, GAUNTLET_TOML_TEMPLATE))
    if agent == "claude-code":
        entries.append((SETTINGS_PATH, settings_json(read(SETTINGS_PATH), fast_gates)))
        entries.append((CLAUDE_MD, upsert_block(read(CLAUDE_MD), guidance_block())))
    else:
        entries.append((PRECOMMIT_PATH, PRECOMMIT_CONFIG))
        entries.append((WORKFLOW_PATH, GITHUB_WORKFLOW))
    return entries


def write(root: Path, path: Path, content: str) -> Action:
    full = root / path
    if full.is_file() and full.read_text(encoding="utf-8") == content:
        return Action.UNCHANGED
    action = Action.UPDATED if full.exists() else Action.CREATED
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return action
