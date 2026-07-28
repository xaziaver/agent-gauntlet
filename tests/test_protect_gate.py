from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet import locking, registry
from gauntlet.gates import protect
from gauntlet.gates.base import GateContext

PATTERNS = ["gauntlet.toml", "pyproject.toml"]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "gauntlet.toml").write_text("[gates.complexity]\nmax = 6\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    return tmp_path


def _ctx(root: Path) -> GateContext:
    return GateContext(
        project_root=root, src=root / "src", tests=root / "tests", verified_paths=PATTERNS
    )


def _lock(root: Path) -> None:
    updated, _ = locking.approve_all(root, PATTERNS)
    registry.save(updated, locking.lock_path(root))


def test_unlocked_project_passes_by_default(project: Path) -> None:
    """Installing Gauntlet must not immediately fail a project that has not locked yet."""
    result = protect.run(_ctx(project), {})
    assert result.passed is True
    assert "gauntlet lock" in str(result.actual)


def test_unlocked_project_fails_when_require_lock_is_set(project: Path) -> None:
    result = protect.run(_ctx(project), {"require_lock": True})
    assert result.passed is False
    assert "gauntlet lock" in result.diagnostics[0].message


def test_locked_and_unchanged_passes(project: Path) -> None:
    _lock(project)
    result = protect.run(_ctx(project), {"require_lock": True})
    assert result.passed is True
    assert result.actual == "2/2 paths unchanged"


def test_a_weakened_threshold_fails_the_gate(project: Path) -> None:
    _lock(project)
    (project / "gauntlet.toml").write_text("[gates.complexity]\nmax = 99\n")
    result = protect.run(_ctx(project), {})
    assert result.passed is False
    assert result.diagnostics[0].file == "gauntlet.toml"
    assert result.diagnostics[0].symbol == "modified"
    assert "revert" in result.diagnostics[0].message


def test_a_deleted_approved_file_fails_the_gate(project: Path) -> None:
    _lock(project)
    (project / "pyproject.toml").unlink()
    result = protect.run(_ctx(project), {})
    assert result.passed is False
    assert result.diagnostics[0].symbol == "missing"


def test_a_path_that_never_existed_is_not_a_finding(tmp_path: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text("x\n")
    _lock(tmp_path)
    assert protect.run(_ctx(tmp_path), {}).passed is True


def test_a_corrupt_lock_file_is_an_error_not_a_pass(project: Path) -> None:
    locking.lock_path(project).write_text("{not json")
    result = protect.run(_ctx(project), {})
    assert result.passed is False
    assert "unreadable" in (result.error or "")


def test_whitespace_only_reformatting_still_counts_as_a_change(project: Path) -> None:
    """Hashing is exact by design: a human reviews what changed, the tool does not guess."""
    _lock(project)
    (project / "gauntlet.toml").write_text("[gates.complexity]\nmax   =   6\n")
    assert protect.run(_ctx(project), {}).passed is False
