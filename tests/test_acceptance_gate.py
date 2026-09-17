"""Integration tests for the acceptance gate, against a real pytest-bdd project.

This fixture is also the reference layout: features/ at the root, bindings under
tests/steps/, and production code reached through an import the bindings own.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gauntlet import locking, registry, specs
from gauntlet.adapters.base import RunResult
from gauntlet.gates import acceptance
from gauntlet.gates.base import GateContext

FEATURE = """\
Feature: Premium rating

  Scenario: Annual premium
    Given a monthly premium of 100
    Then the annual premium is 1200

  Scenario Outline: Terms
    Given a monthly premium of <monthly>
    Then the annual premium is <annual>

    Examples:
      | monthly | annual |
      | 50      | 600    |
      | 200     | 2400   |
"""

RATING = "def annual(monthly: int) -> int:\n    return monthly * 12\n"

CONFTEST = (
    "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parent / 'src'))\n"
)

BINDINGS = """\
from pytest_bdd import given, parsers, scenarios, then

from rating import annual

scenarios("../../features/rating.feature")


@given(parsers.parse("a monthly premium of {amount:d}"), target_fixture="monthly")
def _monthly(amount: int) -> int:
    return amount


@then(parsers.parse("the annual premium is {expected:d}"))
def _check(monthly: int, expected: int) -> None:
    assert annual(monthly) == expected
"""

DECORATIVE = """\
from pytest_bdd import given, parsers, scenarios, then

scenarios("../../features/rating.feature")


@given(parsers.parse("a monthly premium of {amount:d}"), target_fixture="monthly")
def _monthly(amount: int) -> int:
    return amount


@then(parsers.parse("the annual premium is {expected:d}"))
def _check(monthly: int, expected: int) -> None:
    assert True  # asserts nothing about the values the spec claims to test
"""

SEMIANNUAL = """\
Feature: Semiannual rating

  Scenario Outline: Halves
    Given a base premium of <base>
    Then the semiannual premium is <semi>

    Examples:
      | base | semi |
      | 50   | 300  |
      | 200  | 1200 |
"""

SEMIANNUAL_BINDINGS = """\
from pytest_bdd import given, parsers, scenarios, then

from rating import annual

scenarios("../../features/semiannual.feature")


@given(parsers.parse("a base premium of {amount:d}"), target_fixture="base")
def _base(amount: int) -> int:
    return amount


@then(parsers.parse("the semiannual premium is {expected:d}"))
def _check(base: int, expected: int) -> None:
    assert annual(base) // 2 == expected
"""

# A plain test that fails on any mutation of rating.feature: a cross-file kill.
CROSS_FILE_KILL = f'''
from pathlib import Path

RATING_SPEC = Path(__file__).parents[2] / "features" / "rating.feature"
PRISTINE = """{FEATURE}"""


def test_the_rating_spec_is_untouched() -> None:
    assert RATING_SPEC.read_text() == PRISTINE
'''

CONFIG = {"features": "features/", "steps": "tests/steps", "mutation_sample": 2}

GATED_CONFIG = """\
[project]
language = "python"
src = "src"
tests = "tests"

[gates.acceptance]
features = "features/"
steps = "tests/steps"
"""

BACKUP = Path(".gauntlet") / "mutation-backup"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "features").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "steps").mkdir(parents=True)
    (tmp_path / "features" / "rating.feature").write_text(FEATURE)
    (tmp_path / "src" / "rating.py").write_text(RATING)
    (tmp_path / "conftest.py").write_text(CONFTEST)
    (tmp_path / "tests" / "steps" / "test_rating.py").write_text(BINDINGS)
    return tmp_path


def _ctx(root: Path) -> GateContext:
    return GateContext(project_root=root, src=root / "src", tests=root / "tests")


@pytest.fixture
def two_module_project(project: Path) -> Path:
    """Two specs, each bound by its own step module."""
    (project / "features" / "semiannual.feature").write_text(SEMIANNUAL)
    (project / "tests" / "steps" / "test_semiannual.py").write_text(SEMIANNUAL_BINDINGS)
    _approve(project, "rating", "semiannual")
    return project


def _approve(root: Path, *names: str) -> None:
    paths = [root / "features" / f"{name}.feature" for name in names or ("rating",)]
    registry.save(specs.approve(root, paths), locking.lock_path(root))


class _Recorder:
    """Stands in for `run_acceptance`: notes which spec is mutated and what ran."""

    def __init__(self, root: Path, names: tuple[str, ...]) -> None:
        self.root = root
        self.originals = {n: (root / "features" / n).read_text() for n in names}
        self.calls: list[tuple[str | None, list[Path]]] = []

    def __call__(self, root: Path, targets: Path | list[Path], *_: object) -> RunResult:
        mutated = [
            n for n, t in self.originals.items() if (self.root / "features" / n).read_text() != t
        ]
        paths = list(targets) if isinstance(targets, list) else [targets]
        self.calls.append((mutated[0] if mutated else None, paths))
        return RunResult(passed=True, output="")


def _record_runs(root: Path, monkeypatch: pytest.MonkeyPatch, *names: str) -> _Recorder:
    recorder = _Recorder(root, names or ("rating.feature", "semiannual.feature"))
    monkeypatch.setattr(acceptance.python_adapter, "run_acceptance", recorder)
    return recorder


def test_no_features_passes_vacuously(tmp_path: Path) -> None:
    """Adoption must not break a project that has no specs yet."""
    result = acceptance.run(_ctx(tmp_path), CONFIG)
    assert result.passed is True
    assert result.actual == "no feature files"


def test_unapproved_spec_fails_before_anything_runs(project: Path) -> None:
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert result.diagnostics[0].symbol == "unapproved"
    assert "features/rating.feature" in result.diagnostics[0].file


def test_approved_and_bound_spec_passes(project: Path) -> None:
    _approve(project)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is True, result.diagnostics


def test_an_edited_approved_spec_fails(project: Path) -> None:
    """The core protection: an agent cannot rewrite the spec to match its code."""
    _approve(project)
    (project / "features" / "rating.feature").write_text(
        FEATURE.replace("the annual premium is 1200", "the annual premium is 999")
    )
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert result.diagnostics[0].symbol == "modified"
    assert "spec is the human's artifact" in result.diagnostics[0].message


def test_failing_scenarios_fail_the_gate(project: Path) -> None:
    _approve(project)
    (project / "src" / "rating.py").write_text("def annual(monthly: int) -> int:\n    return 0\n")
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert "scenarios failing" in str(result.actual)


def test_decorative_scenarios_are_caught_by_mutation(project: Path) -> None:
    """Bindings that assert nothing pass the suite — only mutation exposes them."""
    _approve(project)
    (project / "tests" / "steps" / "test_rating.py").write_text(DECORATIVE)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert "surviving mutant" in str(result.actual)
    message = result.diagnostics[0].message
    assert "->" in message  # names the actual mutation
    assert "gauntlet mutant approve" in message  # offers the equivalence route


def test_mutation_restores_the_feature_file(project: Path) -> None:
    """A mutant is a temporary in-place edit; the human's artifact must survive it."""
    _approve(project)
    before = (project / "features" / "rating.feature").read_text()
    acceptance.run(_ctx(project), CONFIG)
    assert (project / "features" / "rating.feature").read_text() == before


def test_mutation_can_be_disabled(project: Path) -> None:
    _approve(project)
    (project / "tests" / "steps" / "test_rating.py").write_text(DECORATIVE)
    result = acceptance.run(_ctx(project), {**CONFIG, "mutate_examples": False})
    assert result.passed is True
    assert "passing" in str(result.actual)


def test_approval_can_be_disabled_for_adoption(project: Path) -> None:
    result = acceptance.run(_ctx(project), {**CONFIG, "require_approved": False})
    assert result.passed is True


def test_a_mutant_runs_only_the_module_that_binds_its_feature(
    two_module_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _record_runs(two_module_project, monkeypatch)
    acceptance.run(_ctx(two_module_project), CONFIG)
    steps = two_module_project / "tests" / "steps"
    mutant_runs = recorder.calls[1:]
    assert len(mutant_runs) == 4  # mutation_sample 2, two specs
    for mutated, targets in mutant_runs:
        assert mutated is not None
        assert targets == [steps / f"test_{Path(mutated).stem}.py"]


def test_a_kill_from_another_module_s_tests_no_longer_counts(two_module_project: Path) -> None:
    """A kill from spec B's tests is not evidence that spec A's rows protect A."""
    steps = two_module_project / "tests" / "steps"
    (steps / "test_rating.py").write_text(DECORATIVE)
    (steps / "test_semiannual.py").write_text(SEMIANNUAL_BINDINGS + CROSS_FILE_KILL)
    scoped = acceptance.run(_ctx(two_module_project), CONFIG)
    assert scoped.passed is False
    assert {d.file for d in scoped.diagnostics} == {"features/rating.feature"}
    whole = acceptance.run(_ctx(two_module_project), {**CONFIG, "scope": "directory"})
    assert whole.passed is True, whole.diagnostics


def test_an_unbound_feature_falls_back_to_the_whole_directory(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / "features" / "orphan.feature").write_text(FEATURE.replace("Premium", "Orphan"))
    _approve(project, "rating", "orphan")
    recorder = _record_runs(project, monkeypatch, "rating.feature", "orphan.feature")
    acceptance.run(_ctx(project), CONFIG)
    steps = project / "tests" / "steps"
    by_spec: dict[str | None, set[tuple[Path, ...]]] = {}
    for mutated, targets in recorder.calls[1:]:
        by_spec.setdefault(mutated, set()).add(tuple(targets))
    assert by_spec == {
        "rating.feature": {(steps / "test_rating.py",)},
        "orphan.feature": {(steps,)},
    }


def test_the_baseline_stage_runs_the_whole_directory(
    two_module_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _record_runs(two_module_project, monkeypatch)
    acceptance.run(_ctx(two_module_project), CONFIG)
    assert recorder.calls[0] == (None, [two_module_project / "tests" / "steps"])


def test_the_scope_record_names_each_feature_s_modules(
    two_module_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_runs(two_module_project, monkeypatch)
    acceptance.run(_ctx(two_module_project), CONFIG)
    record = json.loads((two_module_project / acceptance.SCOPE_RECORD).read_text())
    assert record == {
        "scope": "module",
        "features": {
            "features/rating.feature": ["tests/steps/test_rating.py"],
            "features/semiannual.feature": ["tests/steps/test_semiannual.py"],
        },
    }


class _Killer:
    """Stands in for `run_acceptance`: the baseline passes and every mutant is killed.
    Notes which backups exist at each call."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls = 0
        self.backups_seen: set[str] = set()

    def __call__(self, *_: object) -> RunResult:
        self.calls += 1
        present = (self.root / BACKUP).rglob("*.feature")
        self.backups_seen.update(p.relative_to(self.root / BACKUP).as_posix() for p in present)
        return RunResult(passed=self.calls == 1, output="")


def _kill_every_mutant(root: Path, monkeypatch: pytest.MonkeyPatch) -> _Killer:
    killer = _Killer(root)
    monkeypatch.setattr(acceptance.python_adapter, "run_acceptance", killer)
    return killer


def test_a_successful_mutation_pass_leaves_no_backup(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backup on disk means a strand; a completed run must not leave one behind."""
    _approve(project)
    killer = _kill_every_mutant(project, monkeypatch)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is True, result.diagnostics
    assert killer.backups_seen == {"features/rating.feature"}
    assert not (project / BACKUP).exists()


def test_backups_mirror_the_spec_s_path_under_the_backup_directory(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two specs of one basename in different directories get two backups, not one."""
    for sub in ("a", "b"):
        (project / "features" / sub).mkdir()
        (project / "features" / sub / "rating.feature").write_text(FEATURE)
    (project / "features" / "rating.feature").unlink()
    _approve(project, "a/rating", "b/rating")
    killer = _kill_every_mutant(project, monkeypatch)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is True, result.diagnostics
    assert killer.backups_seen == {"features/a/rating.feature", "features/b/rating.feature"}
    assert not (project / BACKUP).exists()


def test_a_stranded_spec_is_restored_from_its_backup_at_the_next_run_and_named_in_actual(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _approve(project)
    _kill_every_mutant(project, monkeypatch)
    spec = project / "features" / "rating.feature"
    copy = project / BACKUP / "features" / "rating.feature"
    copy.parent.mkdir(parents=True)
    copy.write_text(FEATURE)
    spec.write_text(FEATURE.replace("is 1200", "is 1201"))  # what a killed run left
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is True, result.diagnostics
    assert result.actual == "1 stranded spec(s) restored; 1 spec(s)"
    assert spec.read_text() == FEATURE
    assert not (project / BACKUP).exists()


def test_a_backup_equal_to_its_spec_is_discarded_without_being_counted(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A kill between the restore and the unlink leaves a backup that strands nothing."""
    _approve(project)
    _kill_every_mutant(project, monkeypatch)
    copy = project / BACKUP / "features" / "rating.feature"
    copy.parent.mkdir(parents=True)
    copy.write_text(FEATURE)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.actual == "1 spec(s)"
    assert not (project / BACKUP).exists()


def test_a_backup_with_no_target_under_features_is_discarded_and_restores_nothing(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An old-layout basename backup, one whose spec was deleted, and one whose
    target lies outside features/ are all discarded and none is written anywhere."""
    _approve(project)
    _kill_every_mutant(project, monkeypatch)
    for rel in ("rating.feature", "features/gone.feature", "src/rating.py"):
        copy = project / BACKUP / rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text("not a spec\n")
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.actual == "1 spec(s)"
    assert not (project / BACKUP).exists()
    assert not (project / "rating.feature").exists()
    assert not (project / "features" / "gone.feature").exists()
    assert (project / "src" / "rating.py").read_text() == RATING


def test_every_spec_write_is_atomic(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each mutant and the restore land by rename, never by writing into the spec."""
    _approve(project)
    _kill_every_mutant(project, monkeypatch)
    spec = project / "features" / "rating.feature"
    replaced: list[Path] = []
    written: list[Path] = []
    real_replace, real_write = os.replace, Path.write_text

    def replace(src: Path, dst: Path) -> None:
        replaced.append(Path(dst))
        real_replace(src, dst)

    def write_text(self: Path, *args: object, **kwargs: object) -> int:
        written.append(self)
        return real_write(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "write_text", write_text)
    acceptance.run(_ctx(project), CONFIG)
    assert replaced.count(spec) == 3  # two sampled mutants, then the restore
    assert spec not in written


def test_a_sigterm_during_mutation_restores_the_spec_and_logs_run_interrupted(
    project: Path,
) -> None:
    """The real thing: `gauntlet check` in a subprocess, killed with the mutation in flight."""
    rows = "".join(f"      | {m:<7} | {m * 12:<6} |\n" for m in range(10, 66, 7))
    text = FEATURE + rows
    spec = project / "features" / "rating.feature"
    spec.write_text(text)
    _approve(project)
    (project / "gauntlet.toml").write_text(GATED_CONFIG)
    backup = project / BACKUP / "features" / "rating.feature"
    proc = subprocess.Popen(
        [sys.executable, "-c", "from gauntlet.cli import app; app()", "check"],
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    started = time.monotonic()
    while not (backup.is_file() and spec.read_text() != text):
        assert proc.poll() is None, proc.communicate()
        assert time.monotonic() - started < 10, "the mutation stage never began"
        time.sleep(0.02)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=10)
    assert proc.returncode == -signal.SIGTERM  # 143 in a shell
    assert spec.read_text() == text
    assert not (project / BACKUP).exists()
    lines = (project / ".gauntlet" / "events.jsonl").read_text().splitlines()
    log = [json.loads(line) for line in lines]
    assert log[-1]["kind"] == "run.interrupted"
    assert (log[-1]["gate"], log[-1]["signal"]) == ("acceptance", "SIGTERM")
    assert "run.finished" not in {line["kind"] for line in log}


def test_an_approval_failure_says_mutation_was_not_run(project: Path) -> None:
    """The summary names the stage it skipped, so its absence is never inferred."""
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert result.actual == "1 unapproved or modified spec(s); mutation not run"


def test_a_baseline_failure_says_mutation_was_not_run(project: Path) -> None:
    _approve(project)
    (project / "src" / "rating.py").write_text("def annual(monthly: int) -> int:\n    return 0\n")
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is False
    assert result.actual == "1 spec(s), scenarios failing; mutation not run"


def test_a_missing_approval_key_is_reported_and_mutation_is_not_run(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename the human re-approved leaves the old key dangling: red, and nothing runs."""
    _approve(project)
    (project / "features" / "rating.feature").rename(project / "features" / "premium.feature")
    _approve(project, "premium")
    recorder = _record_runs(project, monkeypatch, "premium.feature")
    result = acceptance.run(_ctx(project), CONFIG)
    assert recorder.calls == []
    assert result.passed is False
    findings = [(d.file, d.symbol) for d in result.diagnostics]
    assert findings == [("features/rating.feature", "missing")]
    assert result.actual == "1 unapproved or modified spec(s); mutation not run"


def test_a_green_gate_s_actual_is_unchanged(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _approve(project)
    _kill_every_mutant(project, monkeypatch)
    result = acceptance.run(_ctx(project), CONFIG)
    assert result.passed is True
    assert result.actual == "1 spec(s)"
