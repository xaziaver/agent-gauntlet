from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet.gates import boundary
from gauntlet.gates.base import GateContext

BOUND = """from pytest_bdd import given, scenarios

from tests.api.rating import quote

scenarios("../../features/rating.feature")
"""

LEAKY = """from pytest_bdd import given, scenarios

from claimgate.domain.triage import assign_severity

scenarios("../../features/rating.feature")
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    package = tmp_path / "src" / "claimgate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    return tmp_path


def _ctx(root: Path) -> GateContext:
    return GateContext(project_root=root, src=root / "src", tests=root / "tests")


def test_production_packages_finds_packages_and_modules(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "claimgate").mkdir(parents=True)
    (src / "claimgate" / "__init__.py").write_text("")
    (src / "helper.py").write_text("x = 1\n")
    (src / "notapackage").mkdir()
    assert boundary.production_packages(src) == {"claimgate", "helper"}


def test_imported_roots_reports_both_import_forms() -> None:
    source = "import claimgate.domain\nfrom claimgate.triage import x\nimport os\n"
    assert boundary.imported_roots(source) == [("claimgate", 1), ("claimgate", 2), ("os", 3)]


def test_relative_imports_are_not_checked() -> None:
    """They stay inside the test tree by construction."""
    assert boundary.imported_roots("from ..api import quote\n") == []


def test_unparsable_source_is_skipped_not_reported_twice() -> None:
    assert boundary.imported_roots("def oops(:\n") == []


def test_a_step_file_importing_the_test_api_passes(project: Path) -> None:
    (project / "tests" / "steps" / "test_rating.py").write_text(BOUND)
    assert boundary.run(_ctx(project), {}).passed is True


def test_a_step_file_importing_production_code_fails(project: Path) -> None:
    (project / "tests" / "steps" / "test_rating.py").write_text(LEAKY)
    result = boundary.run(_ctx(project), {})
    assert result.passed is False
    assert result.diagnostics[0].symbol == "claimgate"
    assert "tests/api" in result.diagnostics[0].message


def test_the_diagnostic_names_the_line(project: Path) -> None:
    (project / "tests" / "steps" / "test_rating.py").write_text(LEAKY)
    assert boundary.run(_ctx(project), {}).diagnostics[0].line == 3


def test_only_the_configured_steps_directory_is_checked(project: Path) -> None:
    """The API layer itself must import production code — that is its job."""
    (project / "tests" / "api").mkdir()
    (project / "tests" / "api" / "rating.py").write_text(
        "from claimgate.domain.triage import assign_severity\n"
    )
    (project / "tests" / "steps" / "test_rating.py").write_text(BOUND)
    assert boundary.run(_ctx(project), {}).passed is True


def test_a_project_without_step_definitions_is_vacuous(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    result = boundary.run(_ctx(tmp_path), {})
    assert result.passed is True
    assert result.vacuous is True


def test_a_project_without_source_packages_is_vacuous(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    assert boundary.run(_ctx(tmp_path), {}).vacuous is True
