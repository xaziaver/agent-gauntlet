from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_run_cmd_reports_a_missing_executable_instead_of_raising(tmp_path: Path) -> None:
    """An uncaught exception in a hook exits 1 and silently disables enforcement."""
    proc = base.run_cmd(["definitely-not-a-real-binary-xyz"], cwd=tmp_path)
    assert proc.returncode == base.MISSING_TOOL_RETURNCODE
    assert "on PATH" in proc.stderr


def test_write_text_atomic_replaces_the_target_and_leaves_no_temp(tmp_path: Path) -> None:
    target = tmp_path / "spec.feature"
    target.write_text("before\n")
    base.write_text_atomic(target, "after\n")
    assert target.read_text() == "after\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spec.feature"]


def test_signals_raise_raises_interrupted_once_and_restores_the_handlers() -> None:
    """The first TERM unwinds as an exception; a repeat while unwinding is ignored."""
    sentinel = signal.signal(signal.SIGTERM, lambda *_: None)
    try:
        installed = signal.getsignal(signal.SIGTERM)
        with pytest.raises(base.Interrupted) as caught, base.signals_raise():
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            finally:
                os.kill(os.getpid(), signal.SIGTERM)  # the repeat: ignored, not re-raised
        assert caught.value.signum == signal.SIGTERM
        assert caught.value.name == "SIGTERM"
        assert signal.getsignal(signal.SIGTERM) is installed
        assert signal.getsignal(signal.SIGHUP) is signal.SIG_DFL
    finally:
        signal.signal(signal.SIGTERM, sentinel)


def test_interrupted_die_ends_the_process_with_the_signal_s_status() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "from gauntlet.gates import base; import signal; "
            "base.Interrupted(signal.SIGTERM).die()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == -signal.SIGTERM  # 143 in a shell
    assert proc.stderr == ""
