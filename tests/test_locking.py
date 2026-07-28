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
    assert set(reg.entries) == {"gauntlet.toml"}
    assert skipped == ["pyproject.toml"]


def test_lock_then_verify_is_clean(tmp_path: Path) -> None:
    root = _project(tmp_path)
    reg, _ = locking.approve_all(root, PATTERNS)
    findings = registry.verify_all(reg, locking.read_subjects(root, PATTERNS))
    assert locking.failures(findings) == []


def test_a_change_after_locking_is_detected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    reg, _ = locking.approve_all(root, PATTERNS)
    (root / "gauntlet.toml").write_text("line = 10\n")  # threshold weakened
    findings = locking.failures(registry.verify_all(reg, locking.read_subjects(root, PATTERNS)))
    assert [f.status for f in findings] == [Status.MODIFIED]


def test_deleting_a_locked_file_is_detected(tmp_path: Path) -> None:
    root = _project(tmp_path)
    reg, _ = locking.approve_all(root, PATTERNS)
    (root / "gauntlet.toml").unlink()
    findings = locking.failures(registry.verify_all(reg, locking.read_subjects(root, PATTERNS)))
    assert [f.status for f in findings] == [Status.MISSING]


def test_a_never_existing_path_is_not_a_finding(tmp_path: Path) -> None:
    """Absent and unapproved is normal; it must not fail the gate."""
    (tmp_path / "gauntlet.toml").write_text("x\n")
    reg, _ = locking.approve_all(tmp_path, PATTERNS)
    findings = registry.verify_all(reg, locking.read_subjects(tmp_path, PATTERNS))
    assert locking.failures(findings) == []
