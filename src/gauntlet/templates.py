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

CONFTEST = '''"""Make src/ importable without installing the package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
'''

PACKAGE_INIT = '"""{package}."""\n'

PLACEHOLDER_MODULE = '''"""Placeholder so the gates have something to measure.

Delete this file and its test as soon as real code lands.
"""


def ready() -> bool:
    """The scaffold is in place."""
    return True
'''

PLACEHOLDER_TEST = """from {package}.placeholder import ready


def test_the_scaffold_is_ready() -> None:
    assert ready() is True
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

# Step definitions must reach the system through a stable test API rather than
# importing production code directly. Enable alongside the acceptance gate.
# [gates.boundary]
# steps = "tests/steps"
# api = "tests/api"

# Acceptance specs are the human's artifact: the agent drafts them, you approve
# them with `gauntlet spec approve`, and an agent editing an approved spec fails
# this gate. Requires pytest-bdd.
# [gates.acceptance]
# features = "features/"
# steps = "tests/steps"
# require_approved = true
# mutate_examples = true

# Mutation testing of the unit tests. Requires mutmut in the project
# environment, plus a [tool.mutmut] section in pyproject.toml:
#     [tool.mutmut]
#     source_paths = ["src/"]
#     pytest_add_cli_args_test_selection = ["tests/"]
# mutmut copies the project into ./mutants, so also add:
#     [tool.pytest.ini_options]
#     addopts = "--ignore=mutants"
# and put `mutants/` and `.mutmut-cache` in .gitignore.
# [gates.mutation]
# min_score = 90
# scope = "changed"      # changed | full
# require_review = false
"""

GUIDANCE_BODY = """\
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
"""
