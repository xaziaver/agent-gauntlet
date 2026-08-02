from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet.adapters import python as adapter

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
