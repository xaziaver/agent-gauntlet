from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gauntlet import config as config_mod
from gauntlet import locking, registry
from gauntlet import mutants as mutants_mod
from gauntlet.adapters import python as python_adapter
from gauntlet.adapters.python import CodeMutant, MutationRun
from gauntlet.gates import mutation
from gauntlet.gates.base import GateContext

SURVIVORS = ["m.x_f__mutmut_2"]
TOTAL = 4  # 3 killed, 1 survived


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def _ctx(root: Path, changed: list[Path] | None = None) -> GateContext:
    return GateContext(
        project_root=root, src=root / "src", tests=root / "tests", changed_files=changed
    )


@pytest.fixture
def fake_mutmut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        python_adapter,
        "run_mutmut",
        lambda *a, **k: MutationRun(ok=True, total=TOTAL, survivors=SURVIVORS),
    )
    monkeypatch.setattr(
        python_adapter, "show_mutant", lambda *a, **k: ("return a > b", "return a >= b")
    )


@pytest.mark.parametrize(
    ("killed", "equivalent", "unresolved", "expected"),
    [(9, 0, 1, 90.0), (10, 0, 0, 100.0), (8, 2, 0, 100.0), (0, 0, 0, 100.0), (1, 0, 3, 25.0)],
)
def test_score_counts_reviewed_equivalents_as_killed(
    killed: int, equivalent: int, unresolved: int, expected: float
) -> None:
    assert mutation.score(killed, equivalent, unresolved) == expected


def test_a_surviving_mutant_below_the_threshold_fails(project: Path, fake_mutmut: None) -> None:
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    assert result.passed is False
    assert "75.0%" in str(result.actual)  # 3 of 4 killed


def test_the_same_run_passes_under_a_lower_threshold(project: Path, fake_mutmut: None) -> None:
    result = mutation.run(_ctx(project), {"min_score": 70, "scope": "full"})
    assert result.passed is True


def test_require_review_fails_on_any_unresolved_survivor(project: Path, fake_mutmut: None) -> None:
    result = mutation.run(_ctx(project), {"min_score": 0, "scope": "full", "require_review": True})
    assert result.passed is False


def test_the_diagnostic_names_the_mutation_and_both_remedies(
    project: Path, fake_mutmut: None
) -> None:
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    message = result.diagnostics[0].message
    assert "return a > b" in message
    assert "Add a test that fails under it" in message
    assert "gauntlet mutant approve-code" in message


def test_changed_scope_with_nothing_changed_skips_the_run(project: Path) -> None:
    result = mutation.run(_ctx(project, changed=[]), {"scope": "changed"})
    assert result.passed is True
    assert result.actual == "no changed modules"


def test_a_mutmut_failure_is_an_error_not_a_pass(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        python_adapter,
        "run_mutmut",
        lambda *a, **k: MutationRun(ok=False, error="could not run 'mutmut'"),
    )
    result = mutation.run(_ctx(project), {"scope": "full"})
    assert result.passed is False
    assert "mutmut" in (result.error or "")


def test_killed_is_derived_from_the_run_total(project: Path, fake_mutmut: None) -> None:
    """`mutmut results` lists only unkilled mutants — counting its lines gave 0 killed."""
    result = mutation.run(_ctx(project), {"min_score": 0, "scope": "full"})
    assert "3 killed" in str(result.actual)


def test_a_copy_failure_is_explained(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mutmut's raw traceback tells an agent nothing actionable."""
    traceback = "FileNotFoundError: [Errno 2] No such file: 'src/gauntlet/.#cli.py'"
    monkeypatch.setattr(
        python_adapter, "run_mutmut", lambda *a, **k: MutationRun(ok=False, error=traceback)
    )
    result = mutation.run(_ctx(project), {"scope": "full"})
    assert "editor lock" in (result.error or "").lower()


def test_an_unrelated_error_is_passed_through_unchanged() -> None:
    assert mutation.explain("mutmut: no [tool.mutmut]") == "mutmut: no [tool.mutmut]"


def test_code_survivors_for_the_cli_run_cold_too(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`approve-code` and `prune-code` reach mutmut through `survivors_for`, which
    calls the adapter the gate calls: the CLI never sees a warmer tree than the gate."""
    (project / "mutants").mkdir()
    (project / "mutants" / "mutmut-stats.json").write_text("{}")
    present_when_invoked: list[bool] = []

    def fake(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        present_when_invoked.append((project / "mutants").exists())
        stdout = (
            "⠏ 4/4  🎉 3 🫥 0  ⏰ 0  🙁 1  🔇 0\n"
            if "run" in args
            else "    m.x_f__mutmut_2: survived\n"
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(python_adapter, "run_cmd", fake)
    monkeypatch.setattr(python_adapter, "show_mutant", lambda *a, **k: ("a > b", "a >= b"))
    survivors = mutation.survivors_for(project, "python", [], 60)
    assert [m.name for m in survivors] == ["m.x_f__mutmut_2"]
    assert present_when_invoked == [False, False]


NOTHING_MATCHES = (
    "Traceback (most recent call last):\n"
    '  File "mutmut/__main__.py", line 1, in run\n'
    "AssertionError: Filtered for specific mutants, but nothing matches\n"
)
OTHER_FAILURE = (
    "Traceback (most recent call last):\n"
    '  File "mutmut/__main__.py", line 1, in run\n'
    "ModuleNotFoundError: No module named 'pytest'\n"
)


def _mutmut_saying(stderr: str):
    """mutmut's process: no progress line, so no total, and this on stderr."""

    def fake(args: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr=stderr)

    return fake


def test_filters_that_match_no_mutant_are_a_vacuous_pass_that_names_them(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = [project / "src" / "pkg" / "shell" / "io.py"]
    monkeypatch.setattr(python_adapter, "run_cmd", _mutmut_saying(NOTHING_MATCHES))
    result = mutation.run(_ctx(project, changed=changed), {"scope": "changed"})
    assert result.passed is True
    assert result.vacuous is True
    assert result.actual == "no mutants in changed modules: pkg.shell.io*"
    assert result.error is None


def test_a_mutmut_failure_under_filters_is_still_a_tool_failure(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = [project / "src" / "pkg" / "shell" / "io.py"]
    monkeypatch.setattr(python_adapter, "run_cmd", _mutmut_saying(OTHER_FAILURE))
    result = mutation.run(_ctx(project, changed=changed), {"scope": "changed"})
    assert result.passed is False
    assert result.vacuous is False
    assert result.actual is None
    assert "ModuleNotFoundError" in (result.error or "")


def test_no_mutants_on_a_full_run_is_still_a_tool_failure(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whole project with no mutants is a broken configuration, whatever mutmut says."""
    monkeypatch.setattr(python_adapter, "run_cmd", _mutmut_saying(NOTHING_MATCHES))
    result = mutation.run(_ctx(project), {"scope": "full"})
    assert result.passed is False
    assert result.vacuous is False
    assert result.actual is None
    assert "nothing matches" in (result.error or "")


def _survivor(index: int) -> CodeMutant:
    """What `collect` describes for the fake's survivor `index`: each one a distinct mutation."""
    name = f"m.x_f__mutmut_{index}"
    return CodeMutant(name, "m", "f", "a > b", f"a >= b + {index}")


def _mutmut_with(monkeypatch: pytest.MonkeyPatch, total: int, surviving: int) -> None:
    """mutmut reports `total` mutants of which `surviving` survive, each with its own diff."""
    names = [_survivor(i).name for i in range(surviving)]
    monkeypatch.setattr(
        python_adapter,
        "run_mutmut",
        lambda *a, **k: MutationRun(ok=True, total=total, survivors=names),
    )
    monkeypatch.setattr(
        python_adapter,
        "show_mutant",
        lambda root, python, name, *a: ("a > b", _survivor(int(name.rpartition("_")[2])).added),
    )


def _approve_code(project: Path, mutants: list[CodeMutant]) -> None:
    registry.save(
        mutants_mod.approve(project, mutation.SUBJECT, mutants, reason="x"),
        locking.lock_path(project),
    )


ELSEWHERE = CodeMutant("m.x_g__mutmut_0", "m", "g", "return 1", "return 2")


def test_survivors_past_the_inspection_cap_count_as_unresolved_in_the_score(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """160 mutants, 150 survive: the true score is 6.25, not 10 / (10 + 40)."""
    _mutmut_with(monkeypatch, total=160, surviving=150)
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    assert result.passed is False
    assert str(result.actual).startswith("score 6.25%, 10 killed, 150 unresolved")
    assert len(result.diagnostics) == mutation.MAX_SURVIVORS_INSPECTED


def test_the_summary_says_how_many_survivors_were_not_inspected(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mutmut_with(monkeypatch, total=160, surviving=150)
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    assert result.actual == "score 6.25%, 10 killed, 150 unresolved, 110 not inspected"


def test_no_approval_is_called_stale_while_any_survivor_is_uninspected(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An approval past the fortieth survivor matches nothing described; the gate
    cannot tell that from an approval whose mutant died, so it says nothing."""
    _approve_code(project, [ELSEWHERE])
    _mutmut_with(monkeypatch, total=160, surviving=150)
    result = mutation.run(_ctx(project), {"min_score": 0, "scope": "full"})
    assert "stale" not in str(result.actual)
    assert not [d for d in result.diagnostics if d.file == config_mod.LOCK_FILENAME]


def test_require_review_fails_on_uninspected_survivors_alone(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every described survivor is approved; the one past the cap is not, and cannot be."""
    cap = mutation.MAX_SURVIVORS_INSPECTED
    _approve_code(project, [_survivor(i) for i in range(cap)])
    _mutmut_with(monkeypatch, total=50, surviving=cap + 1)
    config = {"min_score": 0, "scope": "full"}
    without = mutation.run(_ctx(project), config)
    assert without.passed is True
    assert without.diagnostics == []
    assert without.actual == (
        f"score 98.0%, 9 killed, 1 unresolved, 1 not inspected, {cap} reviewed-equivalent"
    )
    with_review = mutation.run(_ctx(project), {**config, "require_review": True})
    assert with_review.passed is False
    assert with_review.diagnostics == []


def test_at_or_under_the_cap_the_result_is_what_it_was(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _approve_code(project, [ELSEWHERE])
    _mutmut_with(monkeypatch, total=50, surviving=mutation.MAX_SURVIVORS_INSPECTED)
    result = mutation.run(_ctx(project), {"min_score": 90, "scope": "full"})
    assert result.passed is False
    assert result.actual == "score 20.0%, 10 killed, 40 unresolved, 1 stale approval(s)"
    assert len(result.diagnostics) == mutation.MAX_SURVIVORS_INSPECTED + 1
    assert result.diagnostics[-1].file == config_mod.LOCK_FILENAME
