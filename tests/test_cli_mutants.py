"""CLI tests for `gauntlet mutant`: classifying survivors is a human judgment."""

from __future__ import annotations

import json
import signal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from gauntlet import cli_mutants, locking, registry, specs
from gauntlet import mutants as mutants_mod
from gauntlet.acceptance import gherkin, mutation
from gauntlet.adapters.python import CodeMutant
from gauntlet.cli import app
from gauntlet.cli_support import EXIT_CONFIG_ERROR, EXIT_OK
from gauntlet.gates import acceptance, base
from gauntlet.gates.base import GateContext
from gauntlet.gates.mutation import SUBJECT, MutmutError

runner = CliRunner()

CONFIG = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[gates.acceptance]
features = "features/"
steps = "tests/steps"
"""

FEATURE = """\
Feature: Tiering

  Scenario Outline: Amount decides the tier
    Given an amount of <amount>
    Then the tier is "<tier>"

    Examples:
      | amount | tier     |
      | 75000  | high     |
      | 100    | standard |
"""

RATING = 'def tier(amount: int) -> str:\n    return "high" if amount > 50000 else "standard"\n'

CONFTEST = (
    "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent / 'src'))\n"
)

BINDINGS = """\
from pytest_bdd import given, parsers, scenarios, then

from rating import tier

scenarios("../../features/tiering.feature")


@given(parsers.parse("an amount of {amount:d}"), target_fixture="amount")
def _amount(amount: int) -> int:
    return amount


@then(parsers.parse('the tier is "{expected}"'))
def _check(amount: int, expected: str) -> None:
    assert tier(amount) == expected
"""

# A plain test in a second module that fails on any mutation of tiering.feature.
CROSS_FILE_KILL = f'''\
from pathlib import Path

PRISTINE = """{FEATURE}"""


def test_the_tiering_spec_is_untouched() -> None:
    assert (Path(__file__).parents[2] / "features" / "tiering.feature").read_text() == PRISTINE
'''

CODE_MUTANT = CodeMutant(
    name="m.x_f__mutmut_2",
    module="pkg.rating",
    function="tier",
    removed="return a > b",
    added="return a >= b",
)


def _text(result: Any) -> str:
    if result.output.strip():
        return result.output
    try:
        return result.stderr or ""
    except ValueError:
        return ""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "features").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "tiering.feature").write_text(FEATURE)
    (tmp_path / "src" / "rating.py").write_text(RATING)
    (tmp_path / "conftest.py").write_text(CONFTEST)
    (tmp_path / "tests" / "steps" / "test_tiering.py").write_text(BINDINGS)
    updated = specs.approve(tmp_path, [tmp_path / "features" / "tiering.feature"])
    registry.save(updated, locking.lock_path(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _mutant_keys(project: Path) -> set[str]:
    approved = registry.load(locking.lock_path(project))
    return set(registry.in_namespace(approved, mutants_mod.MUTANT_NAMESPACE).entries)


def test_approve_records_the_surviving_mutants(project: Path) -> None:
    """75000 -> 75001 is still 'high': the spec cannot distinguish them."""
    result = runner.invoke(
        app,
        ["mutant", "approve", "features/tiering.feature", "--reason", "same tier either side"],
    )
    assert result.exit_code == EXIT_OK
    assert _mutant_keys(project)


def test_mutant_approve_scopes_like_the_gate(project: Path) -> None:
    """A second module that would kill tiering's mutants cross-file does not run for them,
    so `approve` records exactly the survivors the scoped gate reports."""
    (project / "tests" / "steps" / "test_other.py").write_text(CROSS_FILE_KILL)
    config = {"features": "features/", "steps": "tests/steps"}
    ctx = GateContext(project_root=project, src=project / "src", tests=project / "tests")
    feature, steps = project / "features" / "tiering.feature", project / "tests" / "steps"
    scoped = acceptance.survivors_for(ctx, config, feature, steps)
    assert scoped
    assert acceptance.survivors_for(ctx, {**config, "scope": "directory"}, feature, steps) == []
    result = runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    assert result.exit_code == EXIT_OK
    key = specs.key_for(project, feature)
    assert _mutant_keys(project) == {
        registry.namespaced(mutants_mod.MUTANT_NAMESPACE, mutants_mod.key_for(key, m))
        for m in scoped
    }


def test_approve_requires_a_reason(project: Path) -> None:
    result = runner.invoke(app, ["mutant", "approve", "features/tiering.feature"])
    assert result.exit_code != EXIT_OK


def test_approve_rejects_a_missing_feature(project: Path) -> None:
    result = runner.invoke(app, ["mutant", "approve", "features/nope.feature", "--reason", "x"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_approved_survivors_stop_failing_the_gate(project: Path) -> None:
    before = runner.invoke(app, ["check", "--gates", "acceptance"])
    assert before.exit_code != EXIT_OK
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "equivalent"])
    after = runner.invoke(app, ["check", "--gates", "acceptance"])
    assert after.exit_code == EXIT_OK
    assert "reviewed-equivalent" in _text(after)


def test_list_shows_the_reason_and_reviewer(project: Path) -> None:
    runner.invoke(
        app,
        [
            "mutant",
            "approve",
            "features/tiering.feature",
            "--reason",
            "both map to high",
            "--reviewer",
            "xaziaver",
        ],
    )
    listed = _text(runner.invoke(app, ["mutant", "list"]))
    assert "both map to high" in listed
    assert "xaziaver" in listed


def test_scenario_filter_narrows_the_approval(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "mutant",
            "approve",
            "features/tiering.feature",
            "--reason",
            "x",
            "--scenario",
            "No such scenario",
        ],
    )
    assert result.exit_code == EXIT_OK
    assert "no surviving mutants" in _text(result)
    assert not _mutant_keys(project)


def test_prune_reports_nothing_when_every_approval_still_applies(project: Path) -> None:
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    result = runner.invoke(app, ["mutant", "prune", "features/tiering.feature"])
    assert result.exit_code == EXIT_OK
    assert "no stale approvals" in _text(result)


def test_prune_removes_only_the_approval_that_no_longer_survives(project: Path) -> None:
    """Tightening one case lapses its judgment; judgments about other cases stand."""
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    assert len(_mutant_keys(project)) == 2

    # 50000 -> 50001 now crosses the threshold, so that mutant dies and its
    # approval is stale. The untouched row is unaffected.
    (project / "features" / "tiering.feature").write_text(
        FEATURE.replace("| 75000  | high     |", "| 50000  | standard |")
    )
    updated = specs.approve(project, [project / "features" / "tiering.feature"])
    registry.save(updated, locking.lock_path(project))

    runner.invoke(app, ["mutant", "prune", "features/tiering.feature"])
    remaining = _mutant_keys(project)
    assert len(remaining) == 1
    assert not any("75000" in key for key in remaining)
    assert any("100|standard" in key for key in remaining)


@pytest.fixture
def fake_code_survivors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_mutants, "survivors_for", lambda *a, **k: [CODE_MUTANT])


def test_approve_code_records_the_survivor(project: Path, fake_code_survivors: None) -> None:
    result = runner.invoke(
        app, ["mutant", "approve-code", "--reason", "unreachable guard", "--reviewer", "x"]
    )
    assert result.exit_code == EXIT_OK
    assert any("pkg.rating" in key for key in _mutant_keys(project))


def test_approve_code_with_nothing_surviving_is_a_no_op(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_mutants, "survivors_for", lambda *a, **k: [])
    result = runner.invoke(app, ["mutant", "approve-code", "--reason", "x"])
    assert result.exit_code == EXIT_OK
    assert "no surviving mutants" in _text(result)


def test_a_mutmut_failure_exits_one(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[CodeMutant]:
        raise MutmutError("could not run 'mutmut'")

    monkeypatch.setattr(cli_mutants, "survivors_for", boom)
    result = runner.invoke(app, ["mutant", "approve-code", "--reason", "x"])
    assert result.exit_code == EXIT_CONFIG_ERROR


def test_code_and_acceptance_approvals_share_one_ledger(
    project: Path, fake_code_survivors: None
) -> None:
    """One ledger, several namespaces — and code keys must not collide with specs."""
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "a"])
    runner.invoke(app, ["mutant", "approve-code", "--reason", "b"])
    keys = _mutant_keys(project)
    assert any(key.startswith(f"mutant:{SUBJECT}#") for key in keys)
    assert any("tiering.feature#" in key for key in keys)


def test_prune_code_removes_an_approval_that_is_gone(
    project: Path, fake_code_survivors: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner.invoke(app, ["mutant", "approve-code", "--reason", "x"])
    assert _mutant_keys(project)
    monkeypatch.setattr(cli_mutants, "survivors_for", lambda *a, **k: [])
    runner.invoke(app, ["mutant", "prune-code"])
    assert not _mutant_keys(project)


def test_prune_code_with_nothing_stale_says_so(project: Path, fake_code_survivors: None) -> None:
    runner.invoke(app, ["mutant", "approve-code", "--reason", "x"])
    result = runner.invoke(app, ["mutant", "prune-code"])
    assert "no stale approvals" in _text(result)


def test_list_shows_code_mutants_too(project: Path, fake_code_survivors: None) -> None:
    runner.invoke(app, ["mutant", "approve-code", "--reason", "provably unreachable"])
    assert "provably unreachable" in _text(runner.invoke(app, ["mutant", "list"]))


def test_mutant_approve_dies_with_the_signal_after_restoring(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate's finally restores the spec; approve's only job is to end as the signal would."""
    died: list[int] = []

    def survivors(*_: object) -> list[Any]:
        raise base.Interrupted(signal.SIGTERM)

    def die(self: base.Interrupted) -> None:
        died.append(self.signum)
        raise SystemExit(128 + self.signum)

    monkeypatch.setattr(acceptance, "survivors_for", survivors)
    monkeypatch.setattr(base.Interrupted, "die", die)
    result = runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    assert died == [signal.SIGTERM]
    assert result.exit_code == 128 + signal.SIGTERM
    assert not (project / ".gauntlet" / "events.jsonl").exists()


ORPHAN = FEATURE.replace("Tiering", "Orphan")


def _add_orphan(project: Path) -> Path:
    """A second approved spec that no step module binds; the lock is rewritten with it."""
    spec = project / "features" / "orphan.feature"
    spec.write_text(ORPHAN)
    registry.save(specs.approve(project, [spec]), locking.lock_path(project))
    return locking.lock_path(project)


def _one_config_error_line(result: Any) -> str:
    assert result.stderr.startswith("config error: ")
    assert result.stderr.count("\n") == 1
    return result.stderr


def test_mutant_approve_refuses_a_spec_that_was_not_measured_and_writes_no_lock(
    project: Path,
) -> None:
    lock = _add_orphan(project)
    before = lock.read_bytes()
    result = runner.invoke(app, ["mutant", "approve", "features/orphan.feature", "--reason", "x"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    said = _one_config_error_line(result)
    assert "features/orphan.feature" in said
    assert "`scenarios(...)`" in said
    assert result.stdout == ""
    assert lock.read_bytes() == before
    assert not _mutant_keys(project)
    assert (project / "features" / "orphan.feature").read_text() == ORPHAN


def test_mutant_prune_refuses_a_spec_that_was_not_measured_and_prunes_nothing(
    project: Path,
) -> None:
    runner.invoke(app, ["mutant", "approve", "features/tiering.feature", "--reason", "x"])
    lock = _add_orphan(project)
    before = lock.read_bytes()
    assert len(_mutant_keys(project)) == 2
    result = runner.invoke(app, ["mutant", "prune", "features/orphan.feature"])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert "features/orphan.feature" in _one_config_error_line(result)
    assert lock.read_bytes() == before
    assert len(_mutant_keys(project)) == 2


# A plain scenario beside the outline, so the preview sees both kinds of mutant.
MIXED = (
    FEATURE
    + """\

  Scenario: A round amount is standard
    Given an amount of 100
    Then the tier is "standard"
"""
)

BACKGROUND_ONLY = """\
Feature: Fixed givens

  Background:
    Given an amount of 100
    And the tier is "standard"
"""


def _expected_listing(text: str, path: Path) -> str:
    found = mutation.mutants(gherkin.parse(text, str(path)))
    return "".join(f"{m.locator}\t{m.signature}\n" for m in found)


def test_preview_lists_every_mutant_the_engine_generates_one_per_line(tmp_path: Path) -> None:
    feature = tmp_path / "mixed.feature"
    feature.write_text(MIXED)
    result = runner.invoke(app, ["mutant", "preview", str(feature)])
    assert result.exit_code == EXIT_OK
    assert result.stdout == _expected_listing(MIXED, feature)
    assert len(result.stdout.splitlines()) > 1


def test_preview_needs_no_project_and_no_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not any((parent / "gauntlet.toml").exists() for parent in [tmp_path, *tmp_path.parents])
    (tmp_path / "candidate.feature").write_text(FEATURE)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["mutant", "preview", "candidate.feature"])
    assert result.exit_code == EXIT_OK
    assert result.stdout == _expected_listing(FEATURE, Path("candidate.feature"))


def test_preview_writes_nothing(project: Path) -> None:
    def snapshot() -> tuple[list[str], bytes]:
        files = sorted(str(p.relative_to(project)) for p in project.rglob("*"))
        return files, locking.lock_path(project).read_bytes()

    assert not (project / ".gauntlet").exists()
    before = snapshot()
    result = runner.invoke(app, ["mutant", "preview", "features/tiering.feature"])
    assert result.exit_code == EXIT_OK
    assert snapshot() == before
    assert not (project / ".gauntlet").exists()


def test_preview_counts_by_kind_on_stderr(tmp_path: Path) -> None:
    feature = tmp_path / "mixed.feature"
    feature.write_text(MIXED)
    found = mutation.mutants(gherkin.parse(MIXED, str(feature)))
    examples = [m for m in found if m.kind == mutation.KIND_EXAMPLE]
    literals = [m for m in found if m.kind == mutation.KIND_LITERAL]
    assert examples and literals
    result = runner.invoke(app, ["mutant", "preview", str(feature)])
    summary = (
        f"{feature}: {len(found)} mutants ({len(examples)} example, {len(literals)} literal)\n"
    )
    assert result.stderr == summary
    assert "mutants (" not in result.stdout


def test_preview_of_a_missing_file_is_a_config_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["mutant", "preview", str(tmp_path / "nope.feature")])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert result.stderr.startswith("config error: ")
    assert result.stderr.count("\n") == 1
    assert result.stdout == ""


def test_preview_of_a_file_that_is_not_utf8_is_a_config_error(tmp_path: Path) -> None:
    feature = tmp_path / "bad.feature"
    feature.write_bytes(b"Feature: x\n\xff\n")
    result = runner.invoke(app, ["mutant", "preview", str(feature)])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert result.stderr.startswith("config error: ")
    assert result.stderr.count("\n") == 1
    assert str(feature) in result.stderr
    assert "11" in result.stderr.replace(str(feature), "")  # the offset, not the path's digits
    assert result.stdout == ""


def test_preview_of_text_with_no_feature_declaration_is_a_config_error(tmp_path: Path) -> None:
    feature = tmp_path / "prose.feature"
    feature.write_text("Scenario: nothing above me\n  Given an amount of 1\n")
    result = runner.invoke(app, ["mutant", "preview", str(feature)])
    assert result.exit_code == EXIT_CONFIG_ERROR
    assert result.stderr.startswith("config error: ")
    assert result.stderr.count("\n") == 1
    assert "no Feature: declaration" in result.stderr
    assert result.stdout == ""


def test_a_background_only_feature_previews_as_zero_mutants_and_exits_zero(tmp_path: Path) -> None:
    feature = tmp_path / "background.feature"
    feature.write_text(BACKGROUND_ONLY)
    result = runner.invoke(app, ["mutant", "preview", str(feature)])
    assert result.exit_code == EXIT_OK
    assert result.stdout == ""
    assert result.stderr == f"{feature}: 0 mutants (0 example, 0 literal)\n"


def test_the_preview_help_says_background_steps_yield_no_mutants() -> None:
    result = runner.invoke(app, ["mutant", "preview", "--help"])
    assert result.exit_code == EXIT_OK
    assert "Background" in result.stdout


# One step carrying two quoted literals and a number, one bare-number step, one outline.
MIGRATION_FEATURE = """\
Feature: Migration

  Scenario: Literals on one line
    Given a "home" policy in "TX" costs 100
    Then the premium is 250

  Scenario Outline: Amount decides the tier
    Given an amount of <amount>
    Then the tier is "<tier>"

    Examples:
      | amount | tier     |
      | 75000  | high     |
      | 100    | standard |
"""

MIGRATION_KEY = "features/migration.feature"
WHEN = "2026-07-28T00:00:00+00:00"


def _version_one_key(mutant: mutation.Mutant) -> str:
    """The key a version-1 ledger held: a literal's locator ended at the step text."""
    locator = mutant.locator
    if mutant.kind == mutation.KIND_LITERAL:
        locator = locator[: locator.rfind("|@")]
    return registry.namespaced(mutants_mod.MUTANT_NAMESPACE, f"{MIGRATION_KEY}#{locator}")


def _approved_at_version_one(mutant: mutation.Mutant, key: str | None = None) -> registry.Registry:
    """An approval as a version-1 writer recorded it, with every payload field set."""
    return registry.approve(
        registry.Registry(),
        key or _version_one_key(mutant),
        mutant.signature.encode("utf-8"),
        when=WHEN,
        reason=f"equivalent: {mutant.signature}",
        reviewer="ada",
    )


def _write_version_one_lock(project: Path, approvals: list[registry.Registry]) -> Path:
    """Merge the approvals into one ledger and write it as version 1, through `save`'s bytes."""
    merged: dict[str, registry.Entry] = {}
    for approval in approvals:
        merged.update(approval.entries)
    lock = locking.lock_path(project)
    registry.save(registry.Registry(entries=merged), lock)
    text = lock.read_text(encoding="utf-8")
    assert text.count('"version": 2') == 1
    lock.write_text(text.replace('"version": 2', '"version": 1'), encoding="utf-8")
    return lock


@pytest.fixture
def migration_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "features").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    (tmp_path / "gauntlet.toml").write_text(CONFIG)
    (tmp_path / "features" / "migration.feature").write_text(MIGRATION_FEATURE)
    (tmp_path / "src" / "rating.py").write_text(RATING)
    (tmp_path / "conftest.py").write_text(CONFTEST)
    (tmp_path / "tests" / "steps" / "test_migration.py").write_text(
        BINDINGS.replace("tiering.feature", "migration.feature")
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _engine_mutants(project: Path) -> list[mutation.Mutant]:
    text = (project / MIGRATION_KEY).read_text(encoding="utf-8")
    return mutation.mutants(gherkin.parse(text, MIGRATION_KEY))


def _entry_lines(text: str, key: str) -> list[str]:
    """The ledger's own lines for one entry, from its key line to its closing brace."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(f'"{key}"'))
    end = next(i for i in range(start, len(lines)) if lines[i].strip() in {"},", "}"})
    return lines[start : end + 1]


def test_migrate_rekeys_literal_approvals_and_preserves_payloads(migration_project: Path) -> None:
    """Two literal approvals move to offset-carrying keys; the example approval and every
    payload are the bytes a version-1 writer left."""
    found = _engine_mutants(migration_project)
    home = next(m for m in found if m.original == '"home"')
    premium = next(m for m in found if m.original == "250")
    example = next(m for m in found if m.kind == mutation.KIND_EXAMPLE and m.original == "75000")
    lock = _write_version_one_lock(
        migration_project, [_approved_at_version_one(m) for m in (home, premium, example)]
    )
    before = json.loads(lock.read_text(encoding="utf-8"))
    before_text = lock.read_text(encoding="utf-8")

    result = runner.invoke(app, ["mutant", "migrate"])

    assert result.exit_code == EXIT_OK
    after_text = lock.read_text(encoding="utf-8")
    after = json.loads(after_text)
    assert after["version"] == 2
    expected_keys = {
        registry.namespaced(mutants_mod.MUTANT_NAMESPACE, mutants_mod.key_for(MIGRATION_KEY, m))
        for m in (home, premium, example)
    }
    assert set(after["entries"]) == expected_keys
    for mutant in (home, premium):
        new_key = registry.namespaced(
            mutants_mod.MUTANT_NAMESPACE, mutants_mod.key_for(MIGRATION_KEY, mutant)
        )
        assert new_key.endswith(f"|@{mutant.offset}")
        assert after["entries"][new_key] == before["entries"][_version_one_key(mutant)]
    example_key = _version_one_key(example)
    assert after["entries"][example_key] == before["entries"][example_key]
    assert _entry_lines(after_text, example_key) == _entry_lines(before_text, example_key)
    assert sorted(e["approved_at"] for e in after["entries"].values()) == [WHEN] * 3
    moved_lines = [line for line in result.stdout.splitlines() if line.startswith("moved  ")]
    assert len(moved_lines) == 2
    assert not [line for line in result.stdout.splitlines() if line.startswith("unpaired  ")]
    assert registry.load(lock).entries.keys() == expected_keys


def test_migrate_carries_an_unpairable_approval_unchanged(migration_project: Path) -> None:
    """A literal whose step is gone pairs to nothing: its key and payload stay, and it is named."""
    found = _engine_mutants(migration_project)
    premium = next(m for m in found if m.original == "250")
    gone = _version_one_key(premium).replace("Then the premium is 250", "Then the surcharge is 7")
    lock = _write_version_one_lock(migration_project, [_approved_at_version_one(premium, gone)])
    before = json.loads(lock.read_text(encoding="utf-8"))

    result = runner.invoke(app, ["mutant", "migrate"])

    assert result.exit_code == EXIT_OK
    after = json.loads(lock.read_text(encoding="utf-8"))
    assert after["version"] == 2
    assert after["entries"] == before["entries"]
    assert f"unpaired  {gone}" in result.stdout.splitlines()
    assert not [line for line in result.stdout.splitlines() if line.startswith("moved  ")]


def _migrate_expecting_nothing_paired(lock: Path, keys: list[str]) -> None:
    """`migrate` carries every named approval under its old key, payload intact, and says so."""
    before = json.loads(lock.read_text(encoding="utf-8"))

    result = runner.invoke(app, ["mutant", "migrate"])

    assert result.exit_code == EXIT_OK
    after = json.loads(lock.read_text(encoding="utf-8"))
    assert after["version"] == 2
    assert after["entries"] == before["entries"]
    lines = result.stdout.splitlines()
    assert [line for line in lines if line.startswith("unpaired  ")] == [
        f"unpaired  {key}" for key in sorted(keys)
    ]
    assert not [line for line in lines if line.startswith("moved  ")]


def test_migrate_reports_every_literal_approval_of_a_missing_spec_as_unpaired(
    migration_project: Path,
) -> None:
    """A spec that is gone, or that is not UTF-8, enumerates no mutants: each literal approval
    pointing at it is carried unpaired and named, nothing moves, and the version still advances."""
    found = _engine_mutants(migration_project)
    home = next(m for m in found if m.original == '"home"')
    premium = next(m for m in found if m.original == "250")
    keys = [_version_one_key(home), _version_one_key(premium)]
    spec = migration_project / MIGRATION_KEY

    spec.unlink()
    lock = _write_version_one_lock(
        migration_project, [_approved_at_version_one(m) for m in (home, premium)]
    )
    _migrate_expecting_nothing_paired(lock, keys)

    spec.write_bytes(b"\xff\xfe" + MIGRATION_FEATURE.encode("utf-16-le"))
    with pytest.raises(UnicodeDecodeError):
        spec.read_text(encoding="utf-8")
    lock = _write_version_one_lock(
        migration_project, [_approved_at_version_one(m) for m in (home, premium)]
    )
    _migrate_expecting_nothing_paired(lock, keys)


def test_migrate_treats_two_matches_as_unpaired(migration_project: Path) -> None:
    """One step carrying the same literal twice gives two mutants with one version-1 key and one
    signature; `migrate` cannot tell which the approval meant, so it carries the entry unpaired."""
    (migration_project / MIGRATION_KEY).write_text(
        'Feature: Twice\n\n  Scenario: Same literal twice\n    Given "x" then "x"\n'
    )
    found = _engine_mutants(migration_project)
    assert [m.kind for m in found] == [mutation.KIND_LITERAL] * 2
    assert len({_version_one_key(m) for m in found}) == 1
    assert len({m.signature for m in found}) == 1
    assert len({m.locator for m in found}) == 2
    first = found[0]

    lock = _write_version_one_lock(migration_project, [_approved_at_version_one(first)])
    _migrate_expecting_nothing_paired(lock, [_version_one_key(first)])


def test_migrate_is_a_no_op_on_a_current_lock(migration_project: Path) -> None:
    lock = locking.lock_path(migration_project)
    registry.save(_approved_at_version_one(next(iter(_engine_mutants(migration_project)))), lock)
    assert json.loads(lock.read_text(encoding="utf-8"))["version"] == 2
    before = lock.read_bytes()

    result = runner.invoke(app, ["mutant", "migrate"])

    assert result.exit_code == EXIT_OK
    assert result.stdout.count("\n") == 1
    assert "already at schema version 2" in result.stdout
    assert lock.read_bytes() == before

    lock.unlink()
    result = runner.invoke(app, ["mutant", "migrate"])

    assert result.exit_code == EXIT_OK
    assert result.stdout.splitlines() == [f"no {lock.name} to migrate"]
    assert not lock.exists()
