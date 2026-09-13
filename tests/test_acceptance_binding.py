"""The feature-to-module binding is read from the step files, every time."""

from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet.acceptance import binding

SCENARIOS = 'from pytest_bdd import scenarios\n\nscenarios("{target}")\n'
SCENARIO = 'import pytest_bdd\n\npytest_bdd.scenario("{target}", "Some scenario")\n'


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    features = tmp_path / "features"
    steps = tmp_path / "tests" / "steps"
    (features / "sub").mkdir(parents=True)
    steps.mkdir(parents=True)
    (features / "a.feature").write_text("Feature: A\n")
    (features / "sub" / "b.feature").write_text("Feature: B\n")
    return features, steps


def test_a_module_that_binds_a_feature_by_relative_path_is_found(
    layout: tuple[Path, Path],
) -> None:
    features, steps = layout
    (steps / "test_a.py").write_text(SCENARIOS.format(target="../../features/a.feature"))
    (steps / "test_b.py").write_text(SCENARIOS.format(target="../../features/sub/b.feature"))
    assert binding.bound_modules(steps, features / "a.feature") == [steps / "test_a.py"]


def test_a_feature_no_module_binds_maps_to_nothing(layout: tuple[Path, Path]) -> None:
    """Only a string literal binds: a computed path or a bare call names no feature."""
    features, steps = layout
    (steps / "test_b.py").write_text(SCENARIOS.format(target="../../features/sub/b.feature"))
    (steps / "test_dynamic.py").write_text(
        "from pathlib import Path\nfrom pytest_bdd import scenarios\n\n"
        'scenarios(Path("../../features/a.feature"))\nscenarios()\n'
    )
    assert binding.bound_modules(steps, features / "a.feature") == []


def test_two_modules_binding_one_feature_are_both_found(layout: tuple[Path, Path]) -> None:
    features, steps = layout
    (steps / "test_first.py").write_text(SCENARIOS.format(target="../../features/a.feature"))
    (steps / "test_second.py").write_text(SCENARIO.format(target="../../features/a.feature"))
    assert binding.bound_modules(steps, features / "a.feature") == [
        steps / "test_first.py",
        steps / "test_second.py",
    ]


def test_a_directory_argument_binds_every_feature_beneath_it(layout: tuple[Path, Path]) -> None:
    features, steps = layout
    (steps / "test_all.py").write_text(SCENARIOS.format(target="../../features"))
    assert binding.bound_modules(steps, features / "a.feature") == [steps / "test_all.py"]
    assert binding.bound_modules(steps, features / "sub" / "b.feature") == [steps / "test_all.py"]


def test_an_unparsable_step_file_binds_nothing(layout: tuple[Path, Path]) -> None:
    """A file pytest never collects must not crash the gate: it binds nothing."""
    features, steps = layout
    (steps / "test_a.py").write_text(SCENARIOS.format(target="../../features/a.feature"))
    (steps / "test_broken.py").write_text('scenarios("../../features/a.feature"\ndef (:\n')
    (steps / "test_binary.py").write_bytes(b'scenarios("../../features/a.feature")\n\xff\xfe')
    assert binding.bound_modules(steps, features / "a.feature") == [steps / "test_a.py"]


def test_binding_is_reread_from_the_step_files_on_every_call(layout: tuple[Path, Path]) -> None:
    """Nothing is cached: editing a step file between two calls changes the answer."""
    features, steps = layout
    (steps / "test_a.py").write_text(SCENARIOS.format(target="../../features/a.feature"))
    assert binding.bound_modules(steps, features / "a.feature") == [steps / "test_a.py"]
    (steps / "test_a.py").write_text(SCENARIOS.format(target="../../features/sub/b.feature"))
    assert binding.bound_modules(steps, features / "a.feature") == []
    assert binding.bound_modules(steps, features / "sub" / "b.feature") == [steps / "test_a.py"]
