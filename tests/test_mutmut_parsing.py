from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gauntlet.adapters import python as adapter
from gauntlet.gates.base import MISSING_TOOL_RETURNCODE

RESULTS = """\
survived
    proration.x_calculate_proration__mutmut_63: survived
    proration.x_calculate_proration__mutmut_65: survived

killed
    proration.x_to_decimal__mutmut_1: killed
"""


def test_parse_results_groups_by_bucket() -> None:
    buckets = adapter.parse_results(RESULTS)
    assert buckets["survived"] == [
        "proration.x_calculate_proration__mutmut_63",
        "proration.x_calculate_proration__mutmut_65",
    ]
    assert buckets["killed"] == ["proration.x_to_decimal__mutmut_1"]


def test_parse_results_ignores_the_emoji_progress_line() -> None:
    """The spinner is for humans and will break the day an emoji changes."""
    noisy = RESULTS + "\n⠦ 133/133  🎉 131 🫥 0  ⏰ 0  🤔 0  🙁 2  🔇 0\n"
    assert len(adapter.parse_results(noisy)["survived"]) == 2


def test_parse_results_of_a_clean_run_is_empty() -> None:
    assert adapter.parse_results("") == {}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("proration.x_calculate__mutmut_63", ("proration", "calculate")),
        ("pkg.mod.x_helper__mutmut_1", ("pkg.mod", "helper")),
        ("mod.x_x_marks__mutmut_9", ("mod", "x_marks")),
    ],
)
def test_parse_mutant_name(name: str, expected: tuple[str, str]) -> None:
    assert adapter.parse_mutant_name(name) == expected


def test_parse_show_extracts_the_mutation() -> None:
    diff = """\
--- proration.py
+++ proration.py
@@ -161,7 +161,7 @@
     if term_days <= 0:
-        raise ValueError("term must be positive")
+        raise ValueError("XXterm must be positiveXX")
     return term_days
"""
    assert adapter.parse_show(diff) == (
        'raise ValueError("term must be positive")',
        'raise ValueError("XXterm must be positiveXX")',
    )


def test_parse_show_ignores_the_file_headers() -> None:
    removed, added = adapter.parse_show("--- a.py\n+++ b.py\n-x = 1\n+x = 2\n")
    assert (removed, added) == ("x = 1", "x = 2")


def test_locator_is_stable_across_mutmut_renumbering() -> None:
    """mutmut IDs are positional; an unrelated edit above must not lapse approvals."""
    first = adapter.CodeMutant("m.x_f__mutmut_3", "m", "f", "a > b", "a >= b")
    renumbered = adapter.CodeMutant("m.x_f__mutmut_41", "m", "f", "a > b", "a >= b")
    assert first.locator == renumbered.locator


def test_locator_distinguishes_two_mutations_of_the_same_line() -> None:
    minus = adapter.CodeMutant("m.x_f__mutmut_1", "m", "f", "a + b", "a - b")
    times = adapter.CodeMutant("m.x_f__mutmut_2", "m", "f", "a + b", "a * b")
    assert minus.locator != times.locator


def test_module_filter_translates_paths_to_dotted_names(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    changed = [src / "pkg" / "rating.py", src / "pkg" / "__init__.py"]
    assert adapter.module_filter(src, changed) == ["pkg*", "pkg.rating*"]


def test_module_filter_skips_files_outside_the_source_tree(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    assert adapter.module_filter(src, [tmp_path / "setup.py"]) == []


def test_parse_total_reads_the_progress_fraction() -> None:
    assert adapter.parse_total("⠏ 62/62  🎉 55 🫥 0  ⏰ 0  🙁 7  🔇 0\n") == 62


def test_parse_total_takes_the_largest_fraction_seen() -> None:
    payload = "⠇ 0/62  🎉 0\n⠏ 62/62  🎉 55\n"
    assert adapter.parse_total(payload) == 62


def test_parse_total_of_empty_output_is_zero() -> None:
    assert adapter.parse_total("") == 0


RUN_OUTPUT = "⠏ 62/62  🎉 55 🫥 0  ⏰ 0  🙁 7  🔇 0\n"
RESULTS_OUTPUT = "    policy.x__is_high__mutmut_2: survived\n"


def _proc(stdout: str = "", stderr: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["mutmut"], returncode=code, stdout=stdout, stderr=stderr
    )


def _fake_run_cmd(outputs: list[subprocess.CompletedProcess[str]]):
    """Returns each canned result in turn: `mutmut run`, then `mutmut results`."""
    calls = iter(outputs)

    def fake(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        return next(calls)

    return fake


def test_run_mutmut_reports_total_and_survivors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        adapter, "run_cmd", _fake_run_cmd([_proc(RUN_OUTPUT), _proc(RESULTS_OUTPUT)])
    )
    outcome = adapter.run_mutmut(tmp_path, "python", [], 60)
    assert outcome.ok is True
    assert outcome.total == 62
    assert outcome.survivors == ["policy.x__is_high__mutmut_2"]


def test_run_mutmut_reports_a_missing_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "run_cmd",
        _fake_run_cmd([_proc(stderr="could not run 'mutmut'", code=MISSING_TOOL_RETURNCODE)]),
    )
    outcome = adapter.run_mutmut(tmp_path, "python", [], 60)
    assert outcome.ok is False
    assert "mutmut" in outcome.error


def test_a_run_that_produces_no_mutants_is_an_error_not_a_perfect_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No progress fraction means mutmut never ran; scoring that as 100% would lie."""
    monkeypatch.setattr(
        adapter, "run_cmd", _fake_run_cmd([_proc(stderr="no [tool.mutmut] section")])
    )
    outcome = adapter.run_mutmut(tmp_path, "python", [], 60)
    assert outcome.ok is False
    assert "tool.mutmut" in outcome.error


def test_filters_are_passed_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return _proc(RUN_OUTPUT) if "run" in args else _proc(RESULTS_OUTPUT)

    monkeypatch.setattr(adapter, "run_cmd", fake)
    adapter.run_mutmut(tmp_path, "python", ["pkg.rating*"], 60)
    assert "pkg.rating*" in seen[0]
