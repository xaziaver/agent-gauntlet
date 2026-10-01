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


A_KEY = "features/a.feature"
A_MUTANTS = (
    f"mutant:{A_KEY}#x|example|amount|1|high",
    f"mutant:{A_KEY}#x|literal|Given y|@6",
)


def _ledger(project: Path, *mutant_keys: str) -> registry.Registry:
    """`a.feature` approved, with the named mutant approvals beside it, saved."""
    approved = specs.approve(project, [project / A_KEY])
    for key in mutant_keys:
        approved = registry.approve(approved, key, key.encode(), reason=f"because {key}")
    registry.save(approved, locking.lock_path(project))
    return approved


def _move(project: Path, old: str, new: str) -> None:
    (project / old).rename(project / new)


def test_unapprove_removes_the_spec_key_and_keeps_its_mutant_approvals_while_the_file_exists(
    project: Path,
) -> None:
    before = _ledger(project, *A_MUTANTS)
    updated, done = specs.unapprove(project, [project / A_KEY])
    assert set(updated.entries) == set(A_MUTANTS)
    assert all(updated.entries[k] == before.entries[k] for k in A_MUTANTS)
    assert done == [specs.Unapproved(key=A_KEY, exists=True, mutants=2)]


def test_unapprove_of_a_spec_that_no_longer_exists_removes_its_mutant_approvals_with_it(
    project: Path,
) -> None:
    other = "mutant:features/nested/b.feature#x|example|amount|1|high"
    _ledger(project, *A_MUTANTS, other)
    (project / A_KEY).unlink()
    updated, done = specs.unapprove(project, [project / A_KEY])
    assert set(updated.entries) == {other}
    assert done == [specs.Unapproved(key=A_KEY, exists=False, mutants=2)]


def test_unapprove_of_a_spec_that_is_not_approved_refuses_and_writes_nothing(
    project: Path,
) -> None:
    _ledger(project, *A_MUTANTS)
    ledger = locking.lock_path(project).read_bytes()
    with pytest.raises(specs.SpecError) as refused:
        specs.unapprove(project, [project / A_KEY, project / "features" / "nested" / "b.feature"])
    assert "features/nested/b.feature is not approved" in str(refused.value)
    assert locking.lock_path(project).read_bytes() == ledger


def test_rename_moves_the_spec_key_and_every_mutant_key_with_payloads_untouched(
    project: Path,
) -> None:
    before = _ledger(project, *A_MUTANTS)
    _move(project, A_KEY, "features/z.feature")
    updated, renamed = specs.rename(project, project / A_KEY, project / "features" / "z.feature")
    moved = {k.replace(A_KEY, "features/z.feature"): v for k, v in before.entries.items()}
    assert set(updated.entries) == set(moved)
    assert all(updated.entries[k].digest == v.digest for k, v in moved.items())
    assert all(updated.entries[k].reason == v.reason for k, v in moved.items())
    assert all(updated.entries[k].approved_at == v.approved_at for k, v in moved.items())
    assert renamed == specs.Renamed(old=A_KEY, new="features/z.feature", mutants=2, differs=False)


def test_rename_reports_when_the_content_differs_from_the_approved_digest(
    project: Path,
) -> None:
    _ledger(project)
    _move(project, A_KEY, "features/z.feature")
    (project / "features" / "z.feature").write_text(FEATURE + "    And z\n")
    _, renamed = specs.rename(project, project / A_KEY, project / "features" / "z.feature")
    assert renamed.differs is True


def _refused_rename(project: Path, old: str, new: str) -> str:
    ledger = locking.lock_path(project).read_bytes()
    with pytest.raises(specs.SpecError) as refused:
        specs.rename(project, project / old, project / new)
    assert locking.lock_path(project).read_bytes() == ledger
    return str(refused.value)


def test_rename_refuses_a_new_path_that_is_not_a_file(project: Path) -> None:
    _ledger(project, *A_MUTANTS)
    (project / A_KEY).unlink()
    assert _refused_rename(project, A_KEY, "features/z.feature") == (
        "no such spec: features/z.feature"
    )


def test_rename_refuses_an_old_path_that_still_exists(project: Path) -> None:
    _ledger(project, *A_MUTANTS)
    (project / "features" / "z.feature").write_text(FEATURE)
    message = _refused_rename(project, A_KEY, "features/z.feature")
    assert message.startswith(f"{A_KEY} still exists;")
    assert "`gauntlet spec approve features/z.feature`" in message


def test_rename_refuses_an_old_path_no_approval_names(project: Path) -> None:
    _ledger(project)
    _move(project, "features/nested/b.feature", "features/z.feature")
    message = _refused_rename(project, "features/nested/b.feature", "features/z.feature")
    assert message == "no approval names features/nested/b.feature; nothing written"


@pytest.mark.parametrize("namespace", ["spec", "mutant"])
def test_rename_refuses_a_new_path_that_already_has_approvals(
    project: Path, namespace: str
) -> None:
    """A `mutant:` key alone under the new path refuses as a `spec:` key does."""
    approved = _ledger(project, *A_MUTANTS)
    b_key = "features/nested/b.feature"
    held = f"spec:{b_key}" if namespace == "spec" else f"mutant:{b_key}#x|example|a|1|b"
    registry.save(registry.approve(approved, held, b"held"), locking.lock_path(project))
    (project / b_key).unlink()
    _move(project, A_KEY, b_key)
    assert (
        _refused_rename(project, A_KEY, b_key) == f"{b_key} already has approvals; nothing written"
    )


def test_mutant_keys_are_anchored_on_the_subject_separator(project: Path) -> None:
    decoy = f"mutant:{A_KEY}.bak#x|example|amount|1|high"
    approved = _ledger(project, *A_MUTANTS, decoy, f"spec:{A_KEY}.bak")
    assert specs.mutant_keys(approved, A_KEY) == sorted(A_MUTANTS)
    assert specs.mutant_keys(approved, f"{A_KEY}.bak") == [decoy]
