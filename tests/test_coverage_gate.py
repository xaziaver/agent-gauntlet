from gauntlet.gates.coverage import judge

DATA = {
    "totals": {"percent_covered": 72.0, "num_branches": 10, "covered_branches": 6},
    "files": {
        "src/a.py": {"summary": {"percent_covered": 90.0}, "missing_lines": [4]},
        "src/b.py": {"summary": {"percent_covered": 40.0}, "missing_lines": [1, 2, 3]},
    },
}


def test_aggregate_below_threshold_fails_and_flags_worst_file_first() -> None:
    passed, actual, diagnostics = judge(DATA, line_min=80.0, branch_min=None)
    assert passed is False
    assert actual == {"line": 72.0, "branch": 60.0}
    assert [d.file for d in diagnostics] == ["src/b.py"]
    assert "1, 2, 3" in diagnostics[0].message


def test_passes_exactly_at_the_threshold() -> None:
    data = {"totals": {"percent_covered": 80.0}, "files": {}}
    passed, actual, _ = judge(data, line_min=80.0, branch_min=None)
    assert passed is True
    assert actual == {"line": 80.0}


def test_branch_threshold_can_fail_an_otherwise_passing_run() -> None:
    data = {
        "totals": {"percent_covered": 95.0, "num_branches": 10, "covered_branches": 5},
        "files": {},
    }
    passed, actual, _ = judge(data, line_min=80.0, branch_min=70.0)
    assert passed is False
    assert actual["branch"] == 50.0


def test_absent_branch_data_does_not_fail_the_gate() -> None:
    data = {"totals": {"percent_covered": 95.0, "num_branches": 0}, "files": {}}
    passed, actual, _ = judge(data, line_min=80.0, branch_min=70.0)
    assert passed is True
    assert "branch" not in actual


def test_missing_line_list_is_truncated_with_a_count() -> None:
    data = {
        "totals": {"percent_covered": 10.0},
        "files": {"src/c.py": {"summary": {"percent_covered": 10.0},
                               "missing_lines": list(range(1, 16))}},
    }
    _, _, diagnostics = judge(data, line_min=80.0, branch_min=None)
    assert "(+5 more)" in diagnostics[0].message
