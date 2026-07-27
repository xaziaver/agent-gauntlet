from pathlib import Path

from gauntlet.gates.tests import _counts, parse_junit

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


def test_bare_testsuite_root_is_handled(tmp_path: Path) -> None:
    """pytest emits <testsuites> today, but a bare <testsuite> root must still parse."""
    bare = PASSING.replace("<testsuites>", "").replace("</testsuites>", "")
    counts, _ = parse_junit(_write(tmp_path, bare))
    assert counts["tests"] == 3
