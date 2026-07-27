from gauntlet.gates.size import _function_lengths, _judge_file

SOURCE = """\
class Widget:
    def method(self):
        return 1

    async def slow(self):
        await go()
        return 2


def top():
    return 3
"""


def test_function_lengths_qualifies_methods_and_handles_async() -> None:
    found = {name: length for name, _, length in _function_lengths(SOURCE)}
    assert found["Widget.method"] == 2
    assert found["Widget.slow"] == 3
    assert found["top"] == 2


def test_nested_functions_are_qualified_by_their_parent() -> None:
    source = "def outer():\n    def inner():\n        return 1\n    return inner\n"
    names = [name for name, _, _ in _function_lengths(source)]
    assert "outer.inner" in names


def test_long_function_is_flagged_with_a_remedy() -> None:
    source = "def big():\n" + "    x = 1\n" * 30
    worst, diagnostics = _judge_file("src/big.py", source, max_fn=25, max_mod=300)
    assert worst == 31
    assert len(diagnostics) == 1
    assert diagnostics[0].symbol == "big"
    assert "Extract helper functions" in diagnostics[0].message


def test_long_module_is_flagged_separately() -> None:
    source = "x = 1\n" * 40
    _, diagnostics = _judge_file("src/long.py", source, max_fn=25, max_mod=30)
    assert len(diagnostics) == 1
    assert "Split it" in diagnostics[0].message


def test_clean_file_produces_nothing() -> None:
    worst, diagnostics = _judge_file("src/ok.py", SOURCE, max_fn=25, max_mod=300)
    assert diagnostics == []
    assert worst == 3
