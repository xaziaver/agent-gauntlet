"""Acceptance mutation: prove the specification examples are wired to behavior.

Mutants are targeted edits to the source text at IR-recorded positions, never a
re-render of the IR. A renderer would have to reproduce comments, tags, and
spacing perfectly, and the feature file is the human's artifact, not ours to
reformat.
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from gauntlet.acceptance.gherkin import ExampleTable, Feature, Scenario, Step

MARKER = "_gauntlet"

BOOLEANS = {
    "true": "false",
    "false": "true",
    "yes": "no",
    "no": "yes",
    "on": "off",
    "off": "on",
}

# Quoted strings and bare numbers in step text. Placeholders (<name>) are never
# matched: in an outline the values live in the table, not the step.
LITERAL_PATTERN = re.compile(r"\"[^\"]*\"|'[^']*'|\b\d+\.\d+\b|\b\d+\b")

KIND_EXAMPLE = "example"
KIND_LITERAL = "literal"


class MutationError(Exception):
    """A mutant could not be applied to the text it came from."""


@dataclass(frozen=True)
class Mutant:
    scenario: str
    line: int
    column: int
    original: str
    mutated: str
    kind: str

    @property
    def description(self) -> str:
        return f"line {self.line}: {self.original} -> {self.mutated} (scenario: {self.scenario})"


def _as_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _decimals(value: str) -> int:
    _, _, fraction = value.partition(".")
    return len(fraction)


def _mutate_number(value: str) -> str | None:
    """Smallest meaningful change: if the test checks the value at all, +1 breaks it."""
    integer = _as_int(value)
    if integer is not None:
        return str(integer + 1)
    number = _as_float(value)
    if number is None:
        return None
    return f"{number + 1:.{_decimals(value)}f}"


def _swap(value: str, alternatives: Sequence[str]) -> str:
    """Another value seen in the same column, which discriminates better than noise."""
    return next((a for a in alternatives if a != value), value + MARKER)


def mutate_value(value: str, alternatives: Sequence[str] = ()) -> str:
    """A meaningfully different value of the same shape."""
    stripped = value.strip()
    if not stripped:
        return MARKER
    flipped = BOOLEANS.get(stripped.lower())
    if flipped is not None:
        return flipped
    number = _mutate_number(stripped)
    if number is not None:
        return number
    return _swap(value, alternatives)


def _column_values(table: ExampleTable, column: int) -> list[str]:
    return [row.cells[column].value for row in table.rows if column < len(row.cells)]


def _column_mutants(scenario: str, table: ExampleTable, column: int) -> list[Mutant]:
    alternatives = _column_values(table, column)
    mutants: list[Mutant] = []
    for row in table.rows:
        if column >= len(row.cells):
            continue
        cell = row.cells[column]
        mutated = mutate_value(cell.value, alternatives)
        if mutated == cell.value:
            continue
        mutants.append(
            Mutant(
                scenario=scenario,
                line=cell.line,
                column=cell.column,
                original=cell.value,
                mutated=mutated,
                kind=KIND_EXAMPLE,
            )
        )
    return mutants


def _example_mutants(scenario: Scenario) -> list[Mutant]:
    table = scenario.examples
    if table is None:
        return []
    return [
        mutant
        for column in range(len(table.headers))
        for mutant in _column_mutants(scenario.name, table, column)
    ]


def _step_mutants(scenario: str, step: Step) -> list[Mutant]:
    mutants: list[Mutant] = []
    for match in LITERAL_PATTERN.finditer(step.text):
        original = match.group()
        mutated = mutate_value(original)
        if mutated == original:
            continue
        mutants.append(
            Mutant(
                scenario=scenario,
                line=step.line,
                column=step.column + match.start(),
                original=original,
                mutated=mutated,
                kind=KIND_LITERAL,
            )
        )
    return mutants


def _literal_mutants(scenario: Scenario) -> list[Mutant]:
    """Plain scenarios carry their values inline; outlines carry placeholders."""
    if scenario.is_outline:
        return []
    return [m for step in scenario.steps for m in _step_mutants(scenario.name, step)]


def mutants(feature: Feature) -> list[Mutant]:
    """Every mutant for a feature, in file order."""
    found: list[Mutant] = []
    for scenario in feature.scenarios:
        found.extend(_example_mutants(scenario))
        found.extend(_literal_mutants(scenario))
    return sorted(found, key=lambda m: (m.line, m.column))


def sample(candidates: Sequence[Mutant], limit: int, seed: int = 0) -> list[Mutant]:
    """A deterministic subset. limit <= 0 means all of them."""
    if limit <= 0 or limit >= len(candidates):
        return list(candidates)
    return random.Random(seed).sample(list(candidates), limit)


def apply(text: str, mutant: Mutant) -> str:
    """The feature text with exactly one value changed."""
    lines = text.splitlines(keepends=True)
    index = mutant.line - 1
    if index >= len(lines):
        raise MutationError(f"line {mutant.line} is past the end of the feature")
    line = lines[index]
    end = mutant.column + len(mutant.original)
    if line[mutant.column : end] != mutant.original:
        raise MutationError(
            f"line {mutant.line} no longer contains {mutant.original!r} at column {mutant.column}"
        )
    lines[index] = line[: mutant.column] + mutant.mutated + line[end:]
    return "".join(lines)
