from pathlib import Path

from gauntlet.gates.tests import parse_junit

PASSING = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="0" skipped="1" tests="3" time="0.1">
    <testcase classname="tests.test_math" name="test_adds" file="tests/test_math.py" line="3"/>
    <testcase classname="tests.test_math" name="test_subs" file="tests/test_math.py" line="7"/>
    <testcase classname="tests.test_math" name="test_skip" file="tests/test_math.py" line="11">
      <skipped message="not today"/>
    </testcase>
  </testsuite>
</testsuites>
"""

FAILING = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="1" failures="1" skipped="0" tests="3" time="0.1">
    <testcase classname="tests.test_math" name="test_adds" file="tests/test_math.py" line="3"/>
    <testcase classname="tests.test_math" name="test_subs" file="tests/test_math.py" line="7">
      <failure message="assert 1 == 2">line one
line two
E   assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_math" name="test_boom" file="tests/test_math.py" line="11">
      <error message="ZeroDivisionError">traceback text</error>
    </testcase>
  </testsuite>
</testsuites>
"""


# Five failures: three share one headline, two have their own.
FIVE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="5" skipped="0" tests="5" time="0.1">
    <testcase classname="tests.test_a" name="test_one" file="tests/test_a.py" line="3">
      <failure message="assert 1 == 2">tail one
E   assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_b" name="test_four" file="tests/test_b.py" line="3">
      <failure message="ZeroDivisionError: division by zero">tail four</failure>
    </testcase>
    <testcase classname="tests.test_a" name="test_two" file="tests/test_a.py" line="8">
      <failure message="assert 1 == 2">tail two
E   assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_a" name="test_three" file="tests/test_a.py" line="13">
      <failure message="assert 1 == 2">tail three
E   assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_b" name="test_five" file="tests/test_b.py" line="9">
      <failure message="KeyError: 'x'">tail five</failure>
    </testcase>
  </testsuite>
</testsuites>
"""

# The same file with the three same-headline cases reduced to their first.
FIVE_WITHOUT_THE_REPEATS = FIVE.replace(
    """    <testcase classname="tests.test_a" name="test_two" file="tests/test_a.py" line="8">
      <failure message="assert 1 == 2">tail two
E   assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_a" name="test_three" file="tests/test_a.py" line="13">
      <failure message="assert 1 == 2">tail three
E   assert 1 == 2</failure>
    </testcase>
""",
    "",
)

SAME_WAY = "3 test(s) failed the same way — first: "


def _write(tmp_path: Path, xml: str) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text(xml)
    return path


def test_clean_run_has_no_diagnostics(tmp_path: Path) -> None:
    counts, diagnostics = parse_junit(_write(tmp_path, PASSING))
    assert diagnostics == []
    assert counts["tests"] == 3
    assert counts["skipped"] == 1


def test_failures_and_errors_both_become_diagnostics(tmp_path: Path) -> None:
    counts, diagnostics = parse_junit(_write(tmp_path, FAILING))
    assert counts["failures"] + counts["errors"] == 2
    assert len(diagnostics) == 2
    symbols = {d.symbol for d in diagnostics}
    assert symbols == {"tests.test_math.test_subs", "tests.test_math.test_boom"}


def test_diagnostic_carries_location_headline_and_traceback_tail(tmp_path: Path) -> None:
    _, diagnostics = parse_junit(_write(tmp_path, FAILING))
    failure = next(d for d in diagnostics if d.symbol.endswith("test_subs"))
    assert failure.file == "tests/test_math.py"
    assert failure.line == 7
    assert "assert 1 == 2" in failure.message
    assert "E   assert 1 == 2" in failure.message


def test_failures_with_one_headline_collapse_into_one_diagnostic_carrying_the_count(
    tmp_path: Path,
) -> None:
    """Five failures, three sharing a headline: three diagnostics. The counts are the
    file's, so `actual` never moves; the two lone headlines are byte-identical to
    what a file holding only them yields."""
    counts, diagnostics = parse_junit(_write(tmp_path, FIVE))
    assert counts["failures"] == 5
    assert len(diagnostics) == 3
    collapsed = [d for d in diagnostics if SAME_WAY in d.message]
    assert len(collapsed) == 1
    _, lone = parse_junit(_write(tmp_path, FIVE_WITHOUT_THE_REPEATS))
    assert [d for d in diagnostics if d is not collapsed[0]] == [
        d for d in lone if d.file != "tests/test_a.py"
    ]
    assert [d.symbol for d in diagnostics] == [
        "tests.test_a.test_one",
        "tests.test_b.test_four",
        "tests.test_b.test_five",
    ]


def test_distinct_headlines_are_not_collapsed(tmp_path: Path) -> None:
    """`assert 1 == 2` and `ZeroDivisionError` are two failures, reported as two."""
    _, diagnostics = parse_junit(_write(tmp_path, FAILING))
    assert len(diagnostics) == 2
    assert not any("failed the same way" in d.message for d in diagnostics)


def test_a_collapsed_diagnostic_keeps_the_first_case_s_location_and_tail(tmp_path: Path) -> None:
    _, diagnostics = parse_junit(_write(tmp_path, FIVE))
    [collapsed] = [d for d in diagnostics if SAME_WAY in d.message]
    assert (collapsed.file, collapsed.line, collapsed.symbol) == (
        "tests/test_a.py",
        3,
        "tests.test_a.test_one",
    )
    assert collapsed.message.startswith(SAME_WAY + "tests.test_a.test_one failed: assert 1 == 2")
    assert "tail one" in collapsed.message
    assert "tail two" not in collapsed.message and "tail three" not in collapsed.message
    _, alone = parse_junit(_write(tmp_path, FIVE_WITHOUT_THE_REPEATS))
    first_alone = next(d for d in alone if d.symbol == "tests.test_a.test_one")
    assert collapsed.message == SAME_WAY + first_alone.message


def test_bare_testsuite_root_is_handled(tmp_path: Path) -> None:
    """pytest emits <testsuites> today, but a bare <testsuite> root must still parse."""
    bare = PASSING.replace("<testsuites>", "").replace("</testsuites>", "")
    counts, _ = parse_junit(_write(tmp_path, bare))
    assert counts["tests"] == 3
