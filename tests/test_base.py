from __future__ import annotations

import sys
from pathlib import Path

from gauntlet.gates import base


def _ctx(root: Path, changed: list[Path] | None = None) -> base.GateContext:
    return base.GateContext(
        project_root=root, src=root / "src", tests=root / "tests", changed_files=changed
    )


def test_is_analyzable_accepts_a_real_python_file(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n")
    assert base.is_analyzable(path) is True


def test_is_analyzable_rejects_non_python(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("hi\n")
    assert base.is_analyzable(path) is False


def test_is_analyzable_rejects_a_path_that_vanished(tmp_path: Path) -> None:
    assert base.is_analyzable(tmp_path / "gone.py") is False


def test_is_analyzable_rejects_a_dangling_editor_lock(tmp_path: Path) -> None:
    """Emacs lock files are dangling symlinks — a gate must never crash on one."""
    link = tmp_path / ".#a.py"
    link.symlink_to(tmp_path / "nowhere.py")
    assert base.is_analyzable(link) is False


def test_python_files_walks_src_only(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "a.py").write_text("x = 1\n")
    (pkg / "notes.txt").write_text("nope\n")
    (tmp_path / "outside.py").write_text("x = 1\n")
    assert [p.name for p in _ctx(tmp_path).python_files()] == ["a.py"]


def test_python_files_narrows_to_changed_files_inside_src(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    inside = src / "a.py"
    inside.write_text("x = 1\n")
    outside = tmp_path / "setup.py"
    outside.write_text("x = 1\n")
    assert _ctx(tmp_path, changed=[inside, outside]).python_files() == [inside]


def test_tool_targets_is_the_src_tree_on_a_full_run(tmp_path: Path) -> None:
    assert _ctx(tmp_path).tool_targets() == [str(tmp_path / "src")]


def test_tool_targets_lists_changed_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    changed = src / "a.py"
    changed.write_text("x = 1\n")
    assert _ctx(tmp_path, changed=[changed]).tool_targets() == [str(changed)]


def test_gate_result_to_dict_is_json_ready() -> None:
    result = base.GateResult(
        gate="size",
        passed=False,
        threshold=25,
        actual=30,
        diagnostics=[base.Diagnostic(file="a.py", message="too long")],
    )
    assert result.to_dict()["diagnostics"][0]["file"] == "a.py"


def test_run_cmd_captures_output_without_raising(tmp_path: Path) -> None:
    proc = base.run_cmd(
        [sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"], cwd=tmp_path
    )
    assert proc.returncode == 3
    assert "hi" in proc.stdout


def test_timed_records_a_duration_on_a_frozen_result(tmp_path: Path) -> None:
    @base.timed
    def gate(ctx: base.GateContext, config: dict[str, object]) -> base.GateResult:
        return base.GateResult(gate="x", passed=True, threshold=1, actual=1)

    result = gate(_ctx(tmp_path), {})
    assert result.gate == "x"
    assert result.duration >= 0.0
