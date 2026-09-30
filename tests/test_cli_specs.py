"""CLI tests for the spec sub-app: approval is the human's ceremony."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import locking, registry
from gauntlet.cli import app
from gauntlet.cli_support import EXIT_CONFIG_ERROR, EXIT_OK

runner = CliRunner()

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.acceptance]
features = "features/"
"""

FEATURE = "Feature: Rating\n\n  Scenario: annual\n    Given a monthly premium of 100\n"


def _text(result: Any) -> str:
    if result.output.strip():
        return result.output
    try:
        return result.stderr or ""
    except ValueError:
        return ""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features" / "nested").mkdir(parents=True)
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    (tmp_path / "features" / "nested" / "claims.feature").write_text(FEATURE)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _entries(project: Path) -> set[str]:
    return set(registry.load(locking.lock_path(project)).entries)


def test_approve_records_the_spec_and_reports_it(project: Path) -> None:
    result = runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    assert result.exit_code == EXIT_OK
    assert "approved  features/rating.feature" in _text(result)
    assert _entries(project) == {"spec:features/rating.feature"}


def test_approve_accepts_several_specs_at_once(project: Path) -> None:
    result = runner.invoke(
        app,
        ["spec", "approve", "features/rating.feature", "features/nested/claims.feature"],
    )
    assert result.exit_code == EXIT_OK
    assert _entries(project) == {
        "spec:features/rating.feature",
        "spec:features/nested/claims.feature",
    }


def test_approving_one_spec_leaves_earlier_approvals_alone(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    runner.invoke(app, ["spec", "approve", "features/nested/claims.feature"])
    assert len(_entries(project)) == 2


def test_approve_does_not_disturb_the_config_namespace(project: Path) -> None:
    """One ledger, several namespaces: approving a spec must not drop config approvals."""
    runner.invoke(app, ["lock"])
    config_keys = {k for k in _entries(project) if k.startswith("config:")}
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    assert config_keys <= _entries(project)


def test_re_approving_after_an_edit_updates_the_hash(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    before = registry.load(locking.lock_path(project)).entries["spec:features/rating.feature"]
    (project / "features" / "rating.feature").write_text(FEATURE + "    And a term of 12 months\n")
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    after = registry.load(locking.lock_path(project)).entries["spec:features/rating.feature"]
    assert before.digest != after.digest


def test_approve_of_a_missing_spec_exits_one(project: Path) -> None:
    result = runner.invoke(app, ["spec", "approve", "features/nope.feature"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "no such spec" in _text(result)


def test_approve_outside_a_project_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_list_marks_every_discovered_spec_unapproved_at_first(project: Path) -> None:
    result = runner.invoke(app, ["spec", "list"])
    assert result.exit_code == EXIT_OK
    text = _text(result)
    assert "unapproved" in text
    assert "features/rating.feature" in text
    assert "features/nested/claims.feature" in text


def test_list_marks_an_approved_spec(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    lines = {
        line.split()[1]: line.split()[0]
        for line in _text(runner.invoke(app, ["spec", "list"])).splitlines()
        if line.strip()
    }
    assert lines["features/rating.feature"] == "approved"
    assert lines["features/nested/claims.feature"] == "unapproved"


def test_list_marks_an_edited_spec_modified(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    (project / "features" / "rating.feature").write_text(FEATURE + "    And more\n")
    assert "modified" in _text(runner.invoke(app, ["spec", "list"]))


def test_list_reports_an_approved_spec_that_was_deleted(project: Path) -> None:
    runner.invoke(app, ["spec", "approve", "features/rating.feature"])
    (project / "features" / "rating.feature").unlink()
    assert "missing" in _text(runner.invoke(app, ["spec", "list"]))


def test_list_with_no_specs_says_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["spec", "list"])
    assert result.exit_code == EXIT_OK
    assert _text(result).strip() == ""


RATING = "features/rating.feature"
CLAIMS = "features/nested/claims.feature"


def _seed(project: Path, spec_keys: list[str], mutant_keys: list[str]) -> bytes:
    """Approve the specs through the CLI, add mutant approvals, return the ledger's bytes."""
    assert runner.invoke(app, ["spec", "approve", *spec_keys]).exit_code == EXIT_OK
    approved = registry.load(locking.lock_path(project))
    for key in mutant_keys:
        approved = registry.approve(approved, key, key.encode(), reason="equivalent")
    registry.save(approved, locking.lock_path(project))
    return locking.lock_path(project).read_bytes()


def _mutant(spec: str, row: str) -> str:
    return f"mutant:{spec}#annual|example|premium|{row}"


def _refused(result: Any, project: Path, ledger: bytes, named: str) -> None:
    assert result.exit_code == EXIT_CONFIG_ERROR
    text = _text(result)
    assert text.startswith("config error: ")
    assert named in text
    assert "Traceback" not in text
    assert locking.lock_path(project).read_bytes() == ledger


def test_unapprove_prints_each_spec_and_the_fate_of_its_mutant_approvals(project: Path) -> None:
    (project / "features" / "plain.feature").write_text(FEATURE)
    plain = "features/plain.feature"
    kept, removed = [_mutant(RATING, "1"), _mutant(RATING, "2")], [_mutant(CLAIMS, "1")]
    _seed(project, [RATING, CLAIMS, plain], kept + removed)
    (project / CLAIMS).unlink()
    result = runner.invoke(app, ["spec", "unapprove", RATING, CLAIMS, plain])
    assert result.exit_code == EXIT_OK
    assert _text(result).splitlines() == [
        f"unapproved  {RATING} (2 mutant approval(s) kept)",
        f"unapproved  {CLAIMS} (1 mutant approval(s) removed with it: the spec no longer exists)",
        f"unapproved  {plain}",
    ]
    assert _entries(project) == set(kept)


def test_unapprove_of_an_unapproved_spec_exits_one_and_writes_nothing(project: Path) -> None:
    ledger = _seed(project, [RATING], [_mutant(RATING, "1")])
    result = runner.invoke(app, ["spec", "unapprove", RATING, CLAIMS])
    _refused(result, project, ledger, CLAIMS)


def test_rename_prints_the_move_and_spec_list_reads_the_new_path_approved(project: Path) -> None:
    _seed(project, [RATING], [_mutant(RATING, "1"), _mutant(RATING, "2")])
    (project / RATING).rename(project / "features" / "premium.feature")
    result = runner.invoke(app, ["spec", "rename", RATING, "features/premium.feature"])
    assert result.exit_code == EXIT_OK
    assert _text(result).splitlines() == [
        f"moved  {RATING} -> features/premium.feature (2 mutant approval(s) moved with it)"
    ]
    listed = _text(runner.invoke(app, ["spec", "list"])).splitlines()
    assert listed == [f"unapproved   {CLAIMS}", "approved     features/premium.feature"]


def test_rename_onto_changed_content_names_the_re_approval(project: Path) -> None:
    _seed(project, [RATING], [])
    (project / RATING).unlink()
    (project / "features" / "premium.feature").write_text(FEATURE + "    And more\n")
    result = runner.invoke(app, ["spec", "rename", RATING, "features/premium.feature"])
    assert result.exit_code == EXIT_OK
    assert _text(result).splitlines()[1:] == [
        "  features/premium.feature differs from the approved content: "
        "`gauntlet spec approve features/premium.feature` re-approves it"
    ]
    assert "modified     features/premium.feature" in _text(runner.invoke(app, ["spec", "list"]))


def _new_is_not_a_file(project: Path) -> tuple[str, str, str]:
    (project / RATING).unlink()
    return RATING, "features/premium.feature", "features/premium.feature"


def _old_still_exists(project: Path) -> tuple[str, str, str]:
    (project / "features" / "premium.feature").write_text(FEATURE)
    return RATING, "features/premium.feature", RATING


def _no_approval_names_old(project: Path) -> tuple[str, str, str]:
    (project / "features" / "premium.feature").write_text(FEATURE)
    return "features/loose.feature", "features/premium.feature", "features/loose.feature"


def _new_already_has_approvals(project: Path) -> tuple[str, str, str]:
    (project / RATING).unlink()
    return RATING, CLAIMS, CLAIMS


@pytest.mark.parametrize(
    "arrange",
    [_new_is_not_a_file, _old_still_exists, _no_approval_names_old, _new_already_has_approvals],
)
def test_rename_refusals_exit_one_name_the_reason_and_write_nothing(
    project: Path, arrange: Any
) -> None:
    ledger = _seed(project, [RATING], [_mutant(RATING, "1"), _mutant(CLAIMS, "1")])
    old, new, named = arrange(project)
    result = runner.invoke(app, ["spec", "rename", old, new])
    _refused(result, project, ledger, named)


@pytest.mark.parametrize("command", ["approve", "unapprove", "rename"])
def test_a_spec_path_outside_the_project_is_a_config_error_not_a_traceback(
    project: Path, tmp_path_factory: pytest.TempPathFactory, command: str
) -> None:
    ledger = _seed(project, [RATING], [])
    outside = tmp_path_factory.mktemp("elsewhere") / "x.feature"
    outside.write_text(FEATURE)
    paths = [RATING, str(outside)] if command == "rename" else [str(outside)]
    result = runner.invoke(app, ["spec", command, *paths])
    _refused(result, project, ledger, f"{outside} is outside the project")


def test_rename_leaves_the_survivor_record_untouched(project: Path) -> None:
    _seed(project, [RATING], [_mutant(RATING, "1")])
    record = project / ".gauntlet" / "acceptance-survivors.json"
    record.parent.mkdir()
    record.write_text('{"features/rating.feature": {"spec": "sha256:0", "survivors": []}}\n')
    before = record.read_bytes()
    (project / RATING).rename(project / "features" / "premium.feature")
    result = runner.invoke(app, ["spec", "rename", RATING, "features/premium.feature"])
    assert result.exit_code == EXIT_OK
    assert record.read_bytes() == before
