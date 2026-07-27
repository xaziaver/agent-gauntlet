from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from gauntlet.gates import duplication
from gauntlet.gates.base import GateContext

REPORT = {
    "duplicates": [
        {
            "lines": 12,
            "firstFile": {"name": "src/a.py", "start": 10},
            "secondFile": {"name": "src/b.py", "start": 40},
        },
        {
            "lines": 30,
            "firstFile": {"name": "src/c.py", "start": 1},
            "secondFile": {"name": "src/d.py", "start": 5},
        },
    ]
}

DUPLICATED = """\
def alpha(values):
    total = 0
    for value in values:
        if value > 0:
            total += value * 2
        else:
            total -= value
    return total


def beta(values):
    total = 0
    for value in values:
        if value > 0:
            total += value * 2
        else:
            total -= value
    return total
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def _ctx(root: Path) -> GateContext:
    return GateContext(project_root=root, src=root / "src", tests=root / "tests")


def _proc(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["jscpd"], returncode=0, stdout=stdout, stderr=stderr)


def _writes(report: dict[str, object]):
    """A fake run_cmd that produces the report jscpd would have written."""

    def fake(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        out = Path(args[args.index("--output") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "jscpd-report.json").write_text(json.dumps(report))
        return _proc()

    return fake


def test_parse_orders_the_largest_clone_first(tmp_path: Path) -> None:
    count, diagnostics = duplication.parse_jscpd(REPORT, tmp_path)
    assert count == 2
    assert [d.value for d in diagnostics] == [30, 12]


def test_diagnostic_names_both_sites_and_the_remedy(tmp_path: Path) -> None:
    _, diagnostics = duplication.parse_jscpd(REPORT, tmp_path)
    message = diagnostics[1].message
    assert "src/b.py:40" in message
    assert "Extract the shared logic" in message
    assert diagnostics[1].file == "src/a.py"
    assert diagnostics[1].line == 10


def test_parse_of_a_clean_report_is_empty(tmp_path: Path) -> None:
    assert duplication.parse_jscpd({"duplicates": []}, tmp_path) == (0, [])


def test_command_carries_the_configured_thresholds(project: Path) -> None:
    cmd = duplication._command(_ctx(project), {"min_lines": 7, "min_tokens": 99}, project)
    assert "--min-lines" in cmd
    assert cmd[cmd.index("--min-lines") + 1] == "7"
    assert cmd[cmd.index("--min-tokens") + 1] == "99"


def test_run_passes_on_a_clean_report(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(duplication, "run_cmd", _writes({"duplicates": []}))
    result = duplication.run(_ctx(project), {})
    assert result.passed is True
    assert result.actual == 0


def test_run_fails_when_clones_exceed_the_limit(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(duplication, "run_cmd", _writes(REPORT))
    result = duplication.run(_ctx(project), {"max_duplicate_blocks": 0})
    assert result.passed is False
    assert result.actual == 2


def test_limit_above_zero_tolerates_that_many_clones(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(duplication, "run_cmd", _writes(REPORT))
    assert duplication.run(_ctx(project), {"max_duplicate_blocks": 5}).passed is True


def test_missing_jscpd_explains_how_to_install_it(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory: 'jscpd'")

    monkeypatch.setattr(duplication, "run_cmd", missing)
    result = duplication.run(_ctx(project), {})
    assert result.passed is False
    assert "npm install" in (result.error or "")


def test_absent_report_is_a_tool_error_not_a_pass(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(duplication, "run_cmd", lambda *a, **k: _proc(stderr="jscpd exploded"))
    result = duplication.run(_ctx(project), {})
    assert result.passed is False
    assert "produced no report" in (result.error or "")


@pytest.mark.skipif(shutil.which("jscpd") is None, reason="jscpd (Node) not installed")
def test_real_jscpd_detects_a_copy_pasted_function(project: Path) -> None:
    (project / "src" / "a.py").write_text(DUPLICATED)
    result = duplication.run(_ctx(project), {"min_lines": 5, "min_tokens": 20})
    assert result.passed is False
    assert result.actual >= 1
