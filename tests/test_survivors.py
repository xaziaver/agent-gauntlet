"""The survivor record's read side, shared by `status` and `review`."""

from __future__ import annotations

from pathlib import Path

from gauntlet import config as config_mod
from gauntlet import mutants, status
from gauntlet.acceptance import gherkin, mutation, survivors

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.acceptance]
features = "features/"
"""

OUTLINE = """\
Feature: Tiering

  Scenario Outline: Amount decides the tier
    Given an amount of <amount>
    Then the tier is "<tier>"

    Examples:
      | amount | tier     |
      | 75000  | high     |
      | 100    | standard |
"""


def test_the_reader_returns_the_features_status_lists(tmp_path: Path) -> None:
    """The move: one reader, and `status` lists exactly what it returns while none is approved."""
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features").mkdir()
    record: dict[str, survivors.Measured] = {}
    for name in ("a", "b"):
        spec = tmp_path / "features" / f"{name}.feature"
        spec.write_text(OUTLINE.replace("Tiering", name))
        found = mutation.mutants(gherkin.parse(spec.read_text(), spec.name))[
            : 2 if name == "a" else 1
        ]
        record[f"features/{name}.feature"] = survivors.measured(spec, found)
    survivors.write(tmp_path, record)
    read = survivors.current(tmp_path)
    assert read == {key: m.survivors for key, m in record.items()}
    listed = [
        p.subject
        for p in status.pending(tmp_path, config_mod.load(tmp_path))
        if p.namespace == mutants.MUTANT_NAMESPACE
    ]
    assert len(listed) == 3
    assert listed == [mutants.key_for(key, m) for key, found in read.items() for m in found]
