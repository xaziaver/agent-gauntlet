from __future__ import annotations

from pathlib import Path

import pytest

from gauntlet import locking, registry, specs

FEATURE = "Feature: Rating\n\n  Scenario: x\n    Given y\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "features" / "nested").mkdir(parents=True)
    (tmp_path / "features" / "a.feature").write_text(FEATURE)
    (tmp_path / "features" / "nested" / "b.feature").write_text(FEATURE)
    (tmp_path / "features" / "notes.md").write_text("not a spec")
    return tmp_path


def test_discover_finds_features_recursively_and_ignores_other_files(project: Path) -> None:
    found = [specs.key_for(project, p) for p in specs.discover(project, "features/")]
    assert found == ["features/a.feature", "features/nested/b.feature"]


def test_discover_of_a_missing_directory_is_empty(tmp_path: Path) -> None:
    assert specs.discover(tmp_path, "features/") == []


def test_approve_records_under_the_spec_namespace(project: Path) -> None:
    updated = specs.approve(project, [project / "features" / "a.feature"])
    assert set(updated.entries) == {"spec:features/a.feature"}


def test_approve_rejects_a_missing_spec(project: Path) -> None:
    with pytest.raises(FileNotFoundError):
        specs.approve(project, [project / "features" / "nope.feature"])


def test_approving_one_spec_leaves_others_alone(project: Path) -> None:
    first = specs.approve(project, [project / "features" / "a.feature"])
    registry.save(first, locking.lock_path(project))
    second = specs.approve(project, [project / "features" / "nested" / "b.feature"])
    assert set(second.entries) == {"spec:features/a.feature", "spec:features/nested/b.feature"}


def test_verify_flags_an_unapproved_spec(project: Path) -> None:
    findings = specs.verify(project, specs.discover(project, "features/"), registry.Registry())
    assert {f.status.value for f in findings} == {"unapproved"}


def test_verify_is_clean_after_approval(project: Path) -> None:
    found = specs.discover(project, "features/")
    approved = specs.approve(project, found)
    assert specs.verify(project, found, approved) == []


def test_verify_detects_an_edit(project: Path) -> None:
    found = specs.discover(project, "features/")
    approved = specs.approve(project, found)
    (project / "features" / "a.feature").write_text(FEATURE + "    And z\n")
    assert [f.status.value for f in specs.verify(project, found, approved)] == ["modified"]


def test_status_lines_show_approved_and_unapproved(project: Path) -> None:
    approved = specs.approve(project, [project / "features" / "a.feature"])
    lines = specs.status_lines(project, "features/", approved)
    assert any(line.startswith("approved") and "a.feature" in line for line in lines)
    assert any(line.startswith("unapproved") and "b.feature" in line for line in lines)
