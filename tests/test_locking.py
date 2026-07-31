from __future__ import annotations

from pathlib import Path

from gauntlet import locking, registry
from gauntlet.registry import Status

PATTERNS = ["gauntlet.toml", "pyproject.toml"]


def _project(tmp_path: Path) -> Path:
    (tmp_path / "gauntlet.toml").write_text("line = 95\n")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    return tmp_path


def test_read_subjects_marks_absent_files_as_none(tmp_path: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text("x\n")
    subjects = locking.read_subjects(tmp_path, PATTERNS)
    assert subjects["gauntlet.toml"] == b"x\n"
    assert subjects["pyproject.toml"] is None


def test_approve_all_records_existing_files_and_reports_skips(tmp_path: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text("x\n")
    reg, skipped = locking.approve_all(tmp_path, PATTERNS)
    assert set(reg.entries) == {"config:gauntlet.toml"}
    assert skipped == ["pyproject.toml"]


def test_lock_then_verify_is_clean(tmp_path: Path) -> None:
    root = _project(tmp_path)
    reg, _ = locking.approve_all(root, PATTERNS)
    assert locking.verify_config(root, PATTERNS, reg) == []


def test_a_change_after_locking_is_detected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    reg, _ = locking.approve_all(root, PATTERNS)
    (root / "gauntlet.toml").write_text("line = 10\n")  # threshold weakened
    findings = locking.verify_config(root, PATTERNS, reg)
    assert [f.status for f in findings] == [Status.MODIFIED]


def test_deleting_a_locked_file_is_detected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    reg, _ = locking.approve_all(root, PATTERNS)
    (root / "gauntlet.toml").unlink()
    findings = locking.verify_config(root, PATTERNS, reg)
    assert [f.status for f in findings] == [Status.MISSING]


def test_a_never_existing_path_is_not_a_finding(tmp_path: Path) -> None:
    """Absent and unapproved is normal; it must not fail the gate."""
    (tmp_path / "gauntlet.toml").write_text("x\n")
    reg, _ = locking.approve_all(tmp_path, PATTERNS)
    assert locking.verify_config(tmp_path, PATTERNS, reg) == []


def test_approvals_are_namespaced(tmp_path: Path) -> None:
    (tmp_path / "gauntlet.toml").write_text("x\n")
    reg, _ = locking.approve_all(tmp_path, PATTERNS)
    assert set(reg.entries) == {"config:gauntlet.toml"}


def test_locking_replaces_the_config_namespace_and_leaves_others_alone(tmp_path: Path) -> None:
    """Dropping a path from verified_paths must drop its approval, not orphan it."""
    (tmp_path / "gauntlet.toml").write_text("x\n")
    (tmp_path / "pyproject.toml").write_text("y\n")
    reg, _ = locking.approve_all(tmp_path, PATTERNS)
    reg = registry.approve(reg, "spec:features/a.feature", b"Feature: a\n")
    registry.save(reg, locking.lock_path(tmp_path))

    reduced, _ = locking.approve_all(tmp_path, ["gauntlet.toml"])
    assert set(reduced.entries) == {"config:gauntlet.toml", "spec:features/a.feature"}
