"""Integration tests: each gate's run() against a real temporary project.

These exercise the subprocess plumbing that the pure-function tests skip.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gauntlet import artifacts
from gauntlet.gates import base, complexity, coverage, crap, size, static
from gauntlet.gates import tests as tests_gate

CLEAN = "def add(a: int, b: int) -> int:\n    return a + b\n"

BRANCHY = """\
def messy(a, b, c, d, e, f, g):
    total = 0
    if a: total += 1
    if b: total += 1
    if c: total += 1
    if d: total += 1
    if e: total += 1
    if f: total += 1
    if g: total += 1
    return total
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def ctx_for(root: Path, enabled: list[str] | None = None) -> base.GateContext:
    return base.GateContext(
        project_root=root,
        src=root / "src",
        tests=root / "tests",
        enabled_gates=enabled or [],
    )


def test_size_gate_passes_on_a_clean_project(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    result = size.run(ctx_for(project), {})
    assert result.passed is True


def test_size_gate_flags_a_long_function(project: Path) -> None:
    (project / "src" / "a.py").write_text("def big():\n" + "    x = 1\n" * 30)
    result = size.run(ctx_for(project), {"max_function_lines": 25})
    assert result.passed is False
    assert result.diagnostics[0].symbol == "big"


def test_size_gate_ignores_editor_lock_files(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    (project / "src" / ".#a.py").symlink_to(project / "src" / "nowhere.py")
    assert size.run(ctx_for(project), {}).passed is True


def test_size_gate_survives_undecodable_and_unparsable_files(project: Path) -> None:
    (project / "src" / "binary.py").write_bytes(b"\xff\xfe\x00garbage")
    (project / "src" / "broken.py").write_text("def oops(:\n")
    assert size.run(ctx_for(project), {}).passed is True


def test_complexity_gate_passes_on_simple_code(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    result = complexity.run(ctx_for(project), {"max": 6})
    assert result.passed is True


def test_complexity_gate_flags_deep_branching(project: Path) -> None:
    (project / "src" / "a.py").write_text(BRANCHY)
    result = complexity.run(ctx_for(project), {"max": 6})
    assert result.passed is False
    assert "Extract" in result.diagnostics[0].message


def test_static_gate_reports_findings(project: Path) -> None:
    (project / "src" / "a.py").write_text("import os\ndef f():\n    return undefined_name\n")
    result = static.run(ctx_for(project), {})
    assert result.passed is False
    assert any("ruff" in d.message for d in result.diagnostics)


def test_static_gate_is_clean_on_clean_code(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    assert static.run(ctx_for(project), {}).passed is True


def test_tests_gate_passes_on_a_green_suite(project: Path) -> None:
    (project / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    result = tests_gate.run(ctx_for(project), {})
    assert result.passed is True
    assert result.actual == "1/1 passing"


def test_tests_gate_reports_a_failing_test(project: Path) -> None:
    (project / "tests" / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    result = tests_gate.run(ctx_for(project), {})
    assert result.passed is False
    assert result.diagnostics[0].symbol.endswith("test_bad")


def test_empty_suite_fails_rather_than_passing_vacuously(project: Path) -> None:
    result = tests_gate.run(ctx_for(project), {})
    assert result.passed is False
    assert result.actual == "no tests collected"
    assert "empty suite is not a passing suite" in result.diagnostics[0].message


def test_tests_gate_writes_the_coverage_artifact_when_coverage_is_enabled(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    (project / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    result = tests_gate.run(ctx_for(project, enabled=["tests", "coverage"]), {})
    assert result.passed is True
    assert (project / ".gauntlet" / "coverage.json").exists()


def test_coverage_gate_errors_when_the_artifact_is_missing(project: Path) -> None:
    result = coverage.run(ctx_for(project), {"line": 80})
    assert result.passed is False
    assert "tests gate must run" in (result.error or "")


def test_coverage_gate_errors_on_an_unparsable_artifact(project: Path) -> None:
    (project / ".gauntlet").mkdir()
    (project / ".gauntlet" / "coverage.json").write_text("{not json")
    result = coverage.run(ctx_for(project), {"line": 80})
    assert result.passed is False
    assert "unreadable" in (result.error or "")


def test_coverage_gate_reads_the_artifact(project: Path) -> None:
    (project / ".gauntlet").mkdir()
    (project / ".gauntlet" / "coverage.json").write_text(
        '{"totals": {"percent_covered": 91.0}, "files": {}}'
    )
    result = coverage.run(ctx_for(project), {"line": 80})
    assert result.passed is True
    assert result.actual == {"line": 91.0}


def test_crap_gate_errors_without_the_coverage_artifact(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    result = crap.run(ctx_for(project), {"max": 15})
    assert result.passed is False
    assert "tests gate must run" in (result.error or "")


def test_crap_gate_flags_an_untested_complex_function(project: Path) -> None:
    (project / "src" / "a.py").write_text(BRANCHY)
    (project / "tests" / "test_nothing.py").write_text("def test_nothing():\n    assert True\n")
    tests_gate.run(ctx_for(project, enabled=["tests", "coverage"]), {})
    result = crap.run(ctx_for(project), {"max": 15})
    assert result.passed is False
    assert "CRAP" in result.diagnostics[0].message


def _proc(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["x"], returncode=0, stdout=stdout, stderr=stderr)


def test_complexity_gate_surfaces_a_tool_failure_as_error_not_a_pass(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    monkeypatch.setattr(artifacts, "run_cmd", lambda *a, **k: _proc(stderr="radon exploded"))
    result = complexity.run(ctx_for(project), {"max": 6})
    assert result.passed is False
    assert "no output" in (result.error or "")


def test_crap_gate_surfaces_a_radon_failure(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (project / ".gauntlet").mkdir()
    (project / ".gauntlet" / "coverage.json").write_text('{"files": {}}')
    monkeypatch.setattr(artifacts, "run_cmd", lambda *a, **k: _proc(stdout="{not json"))
    result = crap.run(ctx_for(project), {"max": 15})
    assert result.passed is False
    assert "unparsable" in (result.error or "")


def test_crap_gate_passes_on_a_well_tested_project(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    (project / "tests" / "test_a.py").write_text(
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "from a import add\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n"
    )
    tests_gate.run(ctx_for(project, enabled=["tests", "coverage"]), {})
    assert crap.run(ctx_for(project), {"max": 15}).passed is True


def test_static_gate_reports_unparsable_ruff_output(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    monkeypatch.setattr(static, "run_cmd", lambda *a, **k: _proc(stdout="{not json", stderr="boom"))
    result = static.run(ctx_for(project), {})
    assert result.passed is False
    assert "ruff output unparsable" in (result.error or "")


def test_coverage_artifact_is_written_for_the_crap_gate_too(project: Path) -> None:
    (project / "src" / "a.py").write_text(CLEAN)
    (project / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    tests_gate.run(ctx_for(project, enabled=["tests", "crap"]), {})
    assert (project / ".gauntlet" / "coverage.json").exists()


def test_gates_with_no_files_report_themselves_as_vacuous(project: Path) -> None:
    """Passing with nothing to check is not the same as passing."""
    ctx = base.GateContext(
        project_root=project, src=project / "src", tests=project / "tests", changed_files=[]
    )
    assert size.run(ctx, {}).vacuous is True
    assert complexity.run(ctx, {"max": 6}).vacuous is True
    assert static.run(ctx, {}).vacuous is True


def test_an_empty_source_tree_names_itself_rather_than_mypy(project: Path) -> None:
    """Three gates used to fail here, none of them naming the real cause."""
    result = static.run(ctx_for(project), {})
    assert result.vacuous is True
    assert "no Python files" in str(result.actual)


def test_coverage_distinguishes_a_missing_run_from_an_empty_one(project: Path) -> None:
    (project / ".gauntlet").mkdir()
    (project / ".gauntlet" / "junit.xml").write_text("<testsuites/>")
    result = coverage.run(ctx_for(project), {"line": 90})
    assert "wrote no coverage data" in (result.error or "")
