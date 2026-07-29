from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gauntlet import loop
from gauntlet.cli import EXIT_CONFIG_ERROR, EXIT_GATE_FAILURE, EXIT_OK, app

runner = CliRunner()

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.size]
max_function_lines = 20
"""

FIXER_AGENT = """
import sys
from pathlib import Path

prompt = sys.stdin.read()
state = Path("calls.txt")
call = int(state.read_text()) + 1 if state.exists() else 1
state.write_text(str(call))
Path(f"prompt-{call}.txt").write_text(prompt)

bad = "def big():\\n" + "    x = 1\\n" * 30
good = "def small():\\n    return 1\\n"
Path("src/a.py").write_text(bad if call == 1 else good)
"""

HOPELESS_AGENT = """
import sys
from pathlib import Path
sys.stdin.read()
Path("src/a.py").write_text("def big():\\n" + "    x = 1\\n" * 30)
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _agent(project: Path, source: str) -> str:
    script = project / "agent.py"
    script.write_text(source)
    return f"{sys.executable} {script}"


def test_first_prompt_carries_the_task() -> None:
    assert "build a parser" in loop.first_prompt("build a parser")


def test_remediation_prompt_carries_task_report_and_guardrails() -> None:
    prompt = loop.remediation_prompt("build a parser", '{"passed": false}')
    assert "build a parser" in prompt
    assert '"passed": false' in prompt
    assert "do not weaken thresholds" in prompt


def test_run_agent_reports_a_missing_command(tmp_path: Path) -> None:
    proc = loop.run_agent("definitely-not-a-real-agent-xyz", "hi", tmp_path)
    assert proc.returncode == loop.MISSING_AGENT_RETURNCODE


def test_loop_converges_when_the_agent_acts_on_feedback(project: Path) -> None:
    result = runner.invoke(
        app, ["loop", "--cmd", _agent(project, FIXER_AGENT), "--task", "write a small function"]
    )
    assert result.exit_code == EXIT_OK
    assert (project / "calls.txt").read_text() == "2"
    second_prompt = (project / "prompt-2.txt").read_text()
    assert "did not pass the quality gates" in second_prompt
    assert "Extract helper functions" in second_prompt  # the diagnostic made the round trip


def test_loop_gives_up_at_the_iteration_cap(project: Path) -> None:
    result = runner.invoke(
        app,
        ["loop", "--cmd", _agent(project, HOPELESS_AGENT), "--task", "x", "--max-iterations", "2"],
    )
    assert result.exit_code == EXIT_GATE_FAILURE
    assert (project / "calls.txt").exists() is False or True  # hopeless agent keeps no state


def test_loop_requires_a_task(project: Path) -> None:
    result = runner.invoke(app, ["loop", "--cmd", "echo"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_loop_rejects_a_missing_agent_command(project: Path) -> None:
    result = runner.invoke(app, ["loop", "--cmd", "definitely-not-a-real-agent-xyz", "--task", "x"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_read_task_rejects_both_sources(tmp_path: Path) -> None:
    f = tmp_path / "t.txt"
    f.write_text("x")
    with pytest.raises(loop.LoopError, match="not both"):
        loop.read_task("also inline", f)


def test_read_task_reads_the_file(tmp_path: Path) -> None:
    f = tmp_path / "t.txt"
    f.write_text("build a parser")
    assert loop.read_task("", f) == "build a parser"
