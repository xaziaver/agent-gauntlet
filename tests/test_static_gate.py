from gauntlet.gates.static import parse_mypy, parse_ruff


def test_ruff_findings_include_the_autofix_hint() -> None:
    payload = """[
      {"code": "I001", "message": "Import block is un-sorted",
       "filename": "src/a.py", "location": {"row": 3, "column": 1}, "fix": {"applicability": "safe"}},
      {"code": "F821", "message": "Undefined name `suffix`",
       "filename": "src/b.py", "location": {"row": 49, "column": 8}, "fix": null}
    ]"""
    diagnostics = parse_ruff(payload)
    assert len(diagnostics) == 2
    assert "auto-fixable" in diagnostics[0].message
    assert "auto-fixable" not in diagnostics[1].message
    assert diagnostics[1].line == 49


def test_ruff_empty_output_is_clean() -> None:
    assert parse_ruff("") == []


def test_mypy_notes_and_non_json_lines_are_ignored() -> None:
    payload = "\n".join(
        [
            'Some banner text that is not JSON',
            '{"file": "src/a.py", "line": 12, "code": "no-untyped-def",'
            ' "message": "Function is missing a type annotation", "severity": "error"}',
            '{"file": "src/a.py", "line": 12, "code": null,'
            ' "message": "See https://mypy.rtfd.io", "severity": "note"}',
        ]
    )
    diagnostics = parse_mypy(payload)
    assert len(diagnostics) == 1
    assert diagnostics[0].symbol == "no-untyped-def"
    assert diagnostics[0].line == 12
