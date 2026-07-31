"""Gherkin parsing: feature text -> canonical IR.

The IR is the language-independent layer of the acceptance pipeline. Parsing and
mutation are shared by every adapter; only running the resulting scenarios is
language-specific. Positions (line, column) are recorded so mutants can be made
as targeted edits to the original text rather than by re-rendering the IR — a
renderer would have to reproduce comments, tags, and spacing perfectly, and the
feature file is the human's artifact, not ours to reformat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")
OUTLINE_PREFIXES = ("Scenario Outline:", "Scenario Template:")
SCENARIO_PREFIXES = ("Scenario:", "Example:")
EXAMPLES_PREFIXES = ("Examples:", "Scenarios:")


class GherkinError(Exception):
    """The feature file could not be parsed."""


@dataclass(frozen=True)
class Cell:
    value: str
    line: int
    column: int  # 0-based offset of the value within its line


@dataclass(frozen=True)
class Row:
    cells: list[Cell]
    line: int

    @property
    def values(self) -> list[str]:
        return [c.value for c in self.cells]


@dataclass(frozen=True)
class ExampleTable:
    header: Row
    rows: list[Row]

    @property
    def headers(self) -> list[str]:
        return self.header.values


@dataclass(frozen=True)
class Step:
    keyword: str
    text: str
    line: int
    column: int = 0  # absolute offset of `text` within its raw line


@dataclass
class Scenario:
    name: str
    line: int
    is_outline: bool = False
    steps: list[Step] = field(default_factory=list)
    examples: ExampleTable | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class Feature:
    name: str
    path: str
    scenarios: list[Scenario] = field(default_factory=list)
    background: list[Step] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class _State:
    path: str
    name: str = ""
    background: list[Step] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    pending_tags: list[str] = field(default_factory=list)
    in_background: bool = False
    in_examples: bool = False
    example_rows: list[Row] = field(default_factory=list)

    @property
    def current(self) -> Scenario | None:
        return self.scenarios[-1] if self.scenarios else None


def split_row(line: str, lineno: int) -> Row:
    """`| a | b |` -> cells carrying the column of each value's first character."""
    cells: list[Cell] = []
    offset = line.index("|") + 1
    for segment in line[offset:].split("|")[:-1]:
        stripped = segment.strip()
        column = offset + (segment.index(stripped) if stripped else 0)
        cells.append(Cell(value=stripped, line=lineno, column=column))
        offset += len(segment) + 1
    return Row(cells=cells, line=lineno)


def _close_examples(state: _State) -> None:
    """Attach a finished Examples block to its scenario."""
    if not state.in_examples or not state.example_rows:
        state.in_examples = False
        state.example_rows = []
        return
    scenario = state.current
    if scenario is not None:
        header, *rows = state.example_rows
        scenario.examples = ExampleTable(header=header, rows=rows)
    state.in_examples = False
    state.example_rows = []


def _start_scenario(state: _State, name: str, lineno: int, is_outline: bool) -> None:
    _close_examples(state)
    state.in_background = False
    state.scenarios.append(
        Scenario(name=name, line=lineno, is_outline=is_outline, tags=state.pending_tags)
    )
    state.pending_tags = []


def _add_step(state: _State, step: Step) -> None:
    _close_examples(state)
    target = state.background if state.in_background else None
    if target is None and state.current is not None:
        target = state.current.steps
    if target is None:
        raise GherkinError(f"{state.path}:{step.line}: step outside a scenario")
    target.append(step)


def _match_prefix(line: str, prefixes: tuple[str, ...]) -> str | None:
    """The remainder after the first matching prefix, or None."""
    for prefix in prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def _feed_scenario(state: _State, line: str, lineno: int) -> bool:
    name = _match_prefix(line, OUTLINE_PREFIXES)
    if name is not None:
        _start_scenario(state, name, lineno, is_outline=True)
        return True
    name = _match_prefix(line, SCENARIO_PREFIXES)
    if name is not None:
        _start_scenario(state, name, lineno, is_outline=False)
        return True
    return False


def _feed_keyword(state: _State, line: str, lineno: int) -> bool:
    """Structural keywords. Returns True when the line was consumed."""
    name = _match_prefix(line, ("Feature:",))
    if name is not None:
        state.name = name
        state.tags, state.pending_tags = state.pending_tags, []
        return True
    if line.startswith("Background:"):
        _close_examples(state)
        state.in_background = True
        return True
    return _feed_scenario(state, line, lineno)


def _feed_tags(state: _State, line: str) -> None:
    state.pending_tags.extend(tag for tag in line.split() if tag.startswith("@"))


def _is_examples(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in EXAMPLES_PREFIXES)


def _feed(state: _State, line: str, raw: str, lineno: int) -> None:
    if line.startswith("@"):
        _feed_tags(state, line)
        return
    if _feed_keyword(state, line, lineno):
        return
    if _is_examples(line):
        _close_examples(state)
        state.in_examples = True
        return
    if line.startswith("|"):
        # The raw line, not the stripped one: columns must be absolute offsets so
        # mutants can be applied as in-place edits to the human's file.
        state.example_rows.append(split_row(raw, lineno))
        return
    _feed_step(state, line, raw, lineno)


def _feed_step(state: _State, line: str, raw: str, lineno: int) -> None:
    for keyword in STEP_KEYWORDS:
        if line.startswith(f"{keyword} "):
            text = line[len(keyword) :].strip()
            _add_step(state, Step(keyword, text, lineno, raw.index(text)))
            return
    # Free text (feature description, scenario narrative) is not part of the IR.


def parse(text: str, path: str = "<string>") -> Feature:
    """Feature text -> IR. Unrecognized prose is ignored, not an error."""
    state = _State(path=path)
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line and not line.startswith("#"):
            _feed(state, line, raw, lineno)
    _close_examples(state)
    if not state.name:
        raise GherkinError(f"{path}: no Feature: declaration found")
    return Feature(
        name=state.name,
        path=path,
        scenarios=state.scenarios,
        background=state.background,
        tags=state.tags,
    )
