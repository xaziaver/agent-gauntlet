from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gauntlet import config as config_mod
from gauntlet import locking, mutants, registry, review, specs, status
from gauntlet.acceptance import gherkin, mutation, report, survivors
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

FEATURE = "Feature: Rating\n\n  Scenario: x\n    Given an amount of 100\n"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "features").mkdir()
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _cfg(project: Path) -> config_mod.Config:
    return config_mod.load(project)


def _items(project: Path) -> list[review.Item]:
    return [review.build_item(project, p) for p in status.pending(project, _cfg(project))]


def _keys(project: Path) -> set[str]:
    return set(registry.load(locking.lock_path(project)).entries)


def test_an_unapproved_spec_shows_its_content(project: Path) -> None:
    item = next(i for i in _items(project) if i.pending.subject.endswith(".feature"))
    assert "Scenario: x" in item.body


def test_a_modified_file_shows_a_diff(project: Path) -> None:
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    (project / "features" / "rating.feature").write_text(
        FEATURE.replace("an amount of 100", "an amount of 999")
    )
    item = next(i for i in _items(project) if i.pending.status == "modified")
    assert "-" in item.body and "+" in item.body
    assert "999" in item.body


def test_a_diff_without_git_history_says_so(tmp_path: Path) -> None:
    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "a.feature").write_text(FEATURE)
    body = review.diff_against_head(tmp_path, "features/a.feature")
    assert "inspect the file directly" in body


def test_a_deleted_subject_is_explained(project: Path) -> None:
    assert "no longer exists" in review.diff_against_head(project, "features/gone.feature")


def test_approving_one_item_leaves_the_others_pending(project: Path) -> None:
    """approve_all replaces the namespace; review must not drop what it did not touch."""
    before = len(_items(project))
    item = _items(project)[0]
    registry.save(review.apply(project, item, "", "me"), locking.lock_path(project))
    assert len(_items(project)) == before - 1


def test_approving_config_paths_one_at_a_time_accumulates(project: Path) -> None:
    first = locking.approve_paths(project, ["gauntlet.toml"])
    registry.save(first, locking.lock_path(project))
    second = locking.approve_paths(project, ["pyproject.toml"])
    assert "config:gauntlet.toml" in second.entries


def test_review_with_an_empty_inbox_says_so(project: Path) -> None:
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    result = runner.invoke(app, ["review"])
    assert result.exit_code == EXIT_OK
    assert "nothing needs your approval" in result.output


def test_skipping_everything_approves_nothing(project: Path) -> None:
    before = _keys(project)
    result = runner.invoke(app, ["review"], input="s\ns\ns\n")
    assert result.exit_code == EXIT_OK
    assert _keys(project) == before
    assert "approved 0 of" in result.output


def test_quitting_stops_the_walk(project: Path) -> None:
    result = runner.invoke(app, ["review"], input="q\n")
    assert "approved 0 of" in result.output


def test_approving_records_the_reviewer_and_clears_the_item(project: Path) -> None:
    result = runner.invoke(app, ["review", "--yes", "--reviewer", "xaziaver"])
    assert result.exit_code == EXIT_OK
    assert _keys(project)
    assert status.pending(project, _cfg(project)) == []


def test_an_invalid_answer_reprompts(project: Path) -> None:
    result = runner.invoke(app, ["review"], input="x\nq\n")
    assert "Please answer" in result.output


def test_the_reviewer_is_recorded_on_a_config_approval(project: Path) -> None:
    """--reviewer was accepted and silently dropped before this."""
    runner.invoke(app, ["review", "--yes", "--reviewer", "xaziaver"])
    entries = registry.load(locking.lock_path(project)).entries
    assert any(e.reviewer == "xaziaver" for e in entries.values())


def test_a_modified_item_requires_a_reason(project: Path) -> None:
    """A changed threshold or spec is the one thing a future reader asks 'why?' about."""
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    (project / "features" / "rating.feature").write_text(FEATURE.replace("100", "999"))

    items = _items(project)
    assert [i.pending.status for i in items] == ["modified"]

    runner.invoke(app, ["review"], input="a\nbecause the rule changed\n")
    entries = registry.load(locking.lock_path(project)).entries
    assert entries["spec:features/rating.feature"].reason == "because the rule changed"


# --- mutants, walked from the survivor record ------------------------------------

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
TIERING = "features/tiering.feature"


def _survivors() -> list[mutation.Mutant]:
    """The two the engine enumerates on the amount column, as the gate would record them."""
    found = mutation.mutants(gherkin.parse(OUTLINE, TIERING))
    return [m for m in found if m.original in ("75000", "100")]


def _key(m: mutation.Mutant) -> str:
    return mutants.key_for(TIERING, m)


@pytest.fixture
def mutant_project(project: Path) -> Path:
    """Config locked, both specs approved, and two survivors recorded: only they wait."""
    spec = project / TIERING
    spec.write_text(OUTLINE)
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    paths = [project / "features" / "rating.feature", spec]
    registry.save(specs.approve(project, paths), locking.lock_path(project))
    measured = survivors.measured(spec, _survivors())
    survivors.write(project, {TIERING: measured})
    return project


def _mutant_entries(project: Path) -> dict[str, registry.Entry]:
    approved = registry.load(locking.lock_path(project))
    return registry.in_namespace(approved, mutants.MUTANT_NAMESPACE).entries


def test_review_shows_a_mutant_as_its_scenario_line_kind_context_and_substitution(
    mutant_project: Path,
) -> None:
    first, second = _items(mutant_project)
    assert first.pending.subject == _key(_survivors()[0])
    assert first.body == (
        "scenario:  Amount decides the tier\n"
        "kind:      example, line 9\n"
        "context:   amount|75000|high\n"
        "mutation:  75000 -> 75001"
    )
    assert first.needs_reason is True
    assert first.mutant == _survivors()[0]
    assert second.body.endswith("context:   amount|100|standard\nmutation:  100 -> 101")
    assert first.title == f"[mutant] {_key(_survivors()[0])} — unapproved"


def test_review_shows_a_re_aimed_mutant_as_modified(mutant_project: Path) -> None:
    """Approved at this locator for another substitution: the diagnostic's sentence, verbatim."""
    re_aimed = _survivors()[1]
    lock = locking.lock_path(mutant_project)
    key = registry.namespaced(mutants.MUTANT_NAMESPACE, _key(re_aimed))
    registry.save(registry.approve(registry.load(lock), key, b"100->999"), lock)
    item = next(i for i in _items(mutant_project) if i.mutant == re_aimed)
    assert item.pending.status == "modified"
    assert item.needs_reason is True
    [diagnostic] = report.by_scenario(TIERING, [re_aimed], [re_aimed])
    sentence = re.search(r"\((approved at this locator[^)]*)\)", diagnostic.message)
    assert sentence is not None
    assert item.body.splitlines()[-1] == sentence.group(1)
    assert "`100->101`" in item.body
    unchanged = next(i for i in _items(mutant_project) if i.mutant != re_aimed)
    assert "approved at this locator" not in unchanged.body


def test_review_records_one_reason_per_mutant(mutant_project: Path) -> None:
    result = runner.invoke(app, ["review", "--reviewer", "h"], input="a\nA\ns\n")
    assert result.exit_code == EXIT_OK
    assert "reason (required)" in result.output
    entries = _mutant_entries(mutant_project)
    first = _survivors()[0]
    assert list(entries) == [registry.namespaced(mutants.MUTANT_NAMESPACE, _key(first))]
    [entry] = entries.values()
    assert (entry.reason, entry.reviewer) == ("A", "h")
    assert entry.digest == registry.digest(first.signature.encode("utf-8"))
    assert result.output.rstrip().endswith("approved 1 of 2 item(s)")
    assert [p.subject for p in status.pending(mutant_project, _cfg(mutant_project))] == [
        _key(_survivors()[1])
    ]


def test_two_mutants_in_one_scenario_get_two_reasons(mutant_project: Path) -> None:
    result = runner.invoke(app, ["review"], input="a\nA\na\nB\n")
    assert result.exit_code == EXIT_OK
    entries = _mutant_entries(mutant_project)
    reasons = {registry.bare(k): e.reason for k, e in entries.items()}
    assert reasons == {_key(_survivors()[0]): "A", _key(_survivors()[1]): "B"}
    assert status.pending(mutant_project, _cfg(mutant_project)) == []


def test_an_empty_reason_for_a_mutant_is_asked_again(mutant_project: Path) -> None:
    """typer.prompt refuses an empty answer: no mutant is ever recorded without a reason."""
    runner.invoke(app, ["review"], input="a\n\nA\nq\n")
    assert [e.reason for e in _mutant_entries(mutant_project).values()] == ["A"]


def test_review_yes_skips_mutants_and_says_how_many_need_a_reason(project: Path) -> None:
    """Config is not locked here, so --yes has one kind of item it does approve."""
    spec = project / TIERING
    spec.write_text(OUTLINE)
    survivors.write(project, {TIERING: survivors.measured(spec, _survivors())})
    waiting = status.pending(project, _cfg(project))
    kinds = [p.namespace for p in waiting]
    assert kinds.count("mutant") == 2
    result = runner.invoke(app, ["review", "--yes"])
    assert result.exit_code == EXIT_OK
    assert _mutant_entries(project) == {}
    approved = len(waiting) - 2
    assert approved > 0
    assert result.output.rstrip().endswith(
        f"approved {approved} of {len(waiting)} item(s). 2 mutant(s) skipped: each needs its "
        f"own reason, and `gauntlet review` without --yes asks for it."
    )
    left = status.pending(project, _cfg(project))
    assert [p.subject for p in left] == [_key(m) for m in _survivors()]


def test_a_mutant_approved_in_review_emits_approval_granted(mutant_project: Path) -> None:
    runner.invoke(app, ["review"], input="a\nA\nq\n")
    log = (mutant_project / ".gauntlet" / "events.jsonl").read_text().splitlines()
    granted = [e for e in map(json.loads, log) if e["kind"] == "approval.granted"]
    assert [(e["namespace"], e["subject"]) for e in granted] == [("mutant", _key(_survivors()[0]))]


def test_a_mutant_approved_in_review_is_one_key_with_one_approved_at(
    mutant_project: Path,
) -> None:
    first = _survivors()[0]
    [item, _] = _items(mutant_project)
    updated = review.apply(mutant_project, item, "A", "h")
    added = set(updated.entries) - _keys(mutant_project)
    assert added == {registry.namespaced(mutants.MUTANT_NAMESPACE, _key(first))}


def test_a_pending_mutant_missing_from_the_record_fails_in_one_line(
    mutant_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record moved between the inbox and the walk: name the key, show nothing."""
    gone = f"{TIERING}#Amount decides the tier|example|amount|5|low"
    stale = status.Pending(namespace="mutant", subject=gone, status="unapproved")
    monkeypatch.setattr(status, "pending", lambda *_: [stale])
    with pytest.raises(review.SurvivorGoneError, match=re.escape(gone)):
        review.build_item(mutant_project, stale)
    result = runner.invoke(app, ["review"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert gone in result.stderr
    assert result.stderr.count("\n") == 1
    assert result.stdout == ""


# --- stale approvals: a subject that was approved and no longer exists ------------

GONE = "features/gone.feature"


def _gone_spec(project: Path, *mutant_rows: str) -> list[str]:
    """Config locked, `rating` and `gone` approved with mutant approvals, then `gone`
    deleted: its `spec:` item is the only thing waiting. Returns the mutant keys."""
    (project / "pyproject.toml").write_text('[project]\nname = "x"\n')
    updated, _ = locking.approve_all(project, _cfg(project).verified_paths)
    registry.save(updated, locking.lock_path(project))
    (project / GONE).write_text(FEATURE)
    approved = specs.approve(project, [project / "features" / "rating.feature", project / GONE])
    keys = [f"mutant:{GONE}#x|example|amount|{row}" for row in mutant_rows]
    kept = "mutant:features/rating.feature#x|example|amount|1"
    for key in [*keys, kept]:
        approved = registry.approve(approved, key, key.encode(), reason="equivalent")
    registry.save(approved, locking.lock_path(project))
    (project / GONE).unlink()
    return keys


def _granted(project: Path) -> list[str]:
    log = project / ".gauntlet" / "events.jsonl"
    lines = log.read_text().splitlines() if log.exists() else []
    return [e["subject"] for e in map(json.loads, lines) if e["kind"] == "approval.granted"]


def test_approving_a_missing_spec_in_review_removes_its_approval_and_its_mutants(
    project: Path,
) -> None:
    removed = _gone_spec(project, "1", "2")
    before = _keys(project)
    result = runner.invoke(app, ["review"], input="a\n")
    assert result.exit_code == EXIT_OK
    assert "Traceback" not in result.output
    assert before - _keys(project) == {f"spec:{GONE}", *removed}
    assert _keys(project) <= before
    assert "mutant:features/rating.feature#x|example|amount|1" in _keys(project)
    assert status.pending(project, _cfg(project)) == []


def test_approving_a_missing_config_path_in_review_removes_its_approval(project: Path) -> None:
    _gone_spec(project)
    registry.save(
        specs.approve(project, [project / "features" / "rating.feature"]),
        locking.lock_path(project),
    )
    registry.save(
        registry.revoke(registry.load(locking.lock_path(project)), f"spec:{GONE}"),
        locking.lock_path(project),
    )
    (project / "pyproject.toml").unlink()
    [item] = _items(project)
    assert item.body == (
        "pyproject.toml was approved but no longer exists. Approving here removes "
        "the stale approval."
    )
    before = _keys(project)
    result = runner.invoke(app, ["review"], input="a\n")
    assert result.exit_code == EXIT_OK
    assert before - _keys(project) == {"config:pyproject.toml"}
    assert _keys(project) <= before
    assert status.pending(project, _cfg(project)) == []


def test_a_missing_spec_item_names_its_mutant_count_and_the_rename_command(
    project: Path,
) -> None:
    _gone_spec(project, "1", "2")
    [item] = _items(project)
    assert item.pending.status == "missing"
    assert item.needs_reason is False
    assert item.body == (
        f"{GONE} was approved but no longer exists. Approving here removes the stale "
        f"approval and its 2 mutant approval(s). If the spec was renamed, "
        f"`gauntlet spec rename {GONE} <new>` carries them instead: skip this item."
    )


def test_a_missing_spec_item_without_mutant_approvals_names_no_count(project: Path) -> None:
    _gone_spec(project)
    [item] = _items(project)
    assert item.body == (
        f"{GONE} was approved but no longer exists. Approving here removes the stale "
        f"approval. If the spec was renamed, `gauntlet spec rename {GONE} <new>` carries "
        f"them instead: skip this item."
    )


def test_removing_a_stale_approval_in_review_emits_no_approval_granted(project: Path) -> None:
    _gone_spec(project, "1")
    (project / "pyproject.toml").unlink()
    assert [i.pending.status for i in _items(project)] == ["missing", "missing"]
    result = runner.invoke(app, ["review"], input="a\na\n")
    assert result.exit_code == EXIT_OK
    assert result.output.rstrip().endswith("approved 2 of 2 item(s)")
    assert _granted(project) == []


def test_review_yes_skips_a_missing_subject_and_says_so(project: Path) -> None:
    """--yes still approves what it can: the new spec beside the missing one."""
    held = _gone_spec(project, "1", "2")
    (project / "features" / "new.feature").write_text(FEATURE)
    before = _keys(project)
    result = runner.invoke(app, ["review", "--yes"])
    assert result.exit_code == EXIT_OK
    assert "carries them instead: skip this item." in result.output
    assert result.output.rstrip().endswith(
        "approved 1 of 2 item(s). 1 stale approval(s) skipped: removing one is a judgment "
        "--yes does not make"
    )
    assert _keys(project) == before | {"spec:features/new.feature"}
    assert {f"spec:{GONE}", *held} <= _keys(project)
    assert _granted(project) == ["features/new.feature"]


def test_review_yes_names_skipped_mutants_and_stale_approvals_in_one_line(
    project: Path,
) -> None:
    (project / GONE).write_text(FEATURE)
    registry.save(specs.approve(project, [project / GONE]), locking.lock_path(project))
    (project / GONE).unlink()
    spec = project / TIERING
    spec.write_text(OUTLINE)
    survivors.write(project, {TIERING: survivors.measured(spec, _survivors())})
    waiting = status.pending(project, _cfg(project))
    result = runner.invoke(app, ["review", "--yes"])
    assert result.exit_code == EXIT_OK
    assert result.output.rstrip().endswith(
        f"approved {len(waiting) - 3} of {len(waiting)} item(s). 2 mutant(s) skipped: each "
        f"needs its own reason, and `gauntlet review` without --yes asks for it. 1 stale "
        f"approval(s) skipped: removing one is a judgment --yes does not make"
    )
    assert f"spec:{GONE}" in _keys(project)
