from gauntlet.gates.complexity import judge

RADON = {
    "src/a.py": [
        {"name": "simple", "lineno": 1, "complexity": 3, "type": "function"},
        {"name": "at_ceiling", "lineno": 10, "complexity": 6, "type": "function"},
        {"name": "method", "classname": "Widget", "lineno": 20, "complexity": 9, "type": "method"},
    ]
}


def test_functions_at_the_ceiling_pass() -> None:
    """CC 6 with max 6 must pass: the gate is `>`, not `>=`."""
    worst, diagnostics = judge({"src/a.py": RADON["src/a.py"][:2]}, ceiling=6)
    assert worst == 6
    assert diagnostics == []


def test_over_ceiling_produces_a_prescriptive_diagnostic() -> None:
    worst, diagnostics = judge(RADON, ceiling=6)
    assert worst == 9
    assert len(diagnostics) == 1
    assert diagnostics[0].symbol == "Widget.method"
    assert diagnostics[0].line == 20
    assert diagnostics[0].value == 9
    assert "Extract" in diagnostics[0].message


def test_radon_parse_errors_are_skipped_not_crashed_on() -> None:
    data = {"src/broken.py": {"error": "invalid syntax"}, **RADON}
    worst, diagnostics = judge(data, ceiling=6)
    assert worst == 9
    assert len(diagnostics) == 1


def test_empty_payload_is_clean() -> None:
    assert judge({}, ceiling=6) == (0, [])
