from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gauntlet import artifacts
from gauntlet.gates.base import GateContext


def _ctx(root: Path, changed: list[Path] | None = None) -> GateContext:
    return GateContext(
        project_root=root, src=root / "src", tests=root / "tests", changed_files=changed
    )


def _proc(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["x"], returncode=0, stdout=stdout, stderr=stderr)


def test_load_coverage_reads_the_artifact(tmp_path: Path) -> None:
    (tmp_path / ".gauntlet").mkdir()
    (tmp_path / ".gauntlet" / "coverage.json").write_text('{"totals": {"percent_covered": 90.0}}')
    assert artifacts.load_coverage(tmp_path)["totals"]["percent_covered"] == 90.0


def test_load_coverage_missing_points_at_the_tests_gate(tmp_path: Path) -> None:
    with pytest.raises(artifacts.ArtifactError, match="tests gate must run"):
        artifacts.load_coverage(tmp_path)


def test_load_coverage_unparsable_is_an_artifact_error(tmp_path: Path) -> None:
    (tmp_path / ".gauntlet").mkdir()
    (tmp_path / ".gauntlet" / "coverage.json").write_text("{not json")
    with pytest.raises(artifacts.ArtifactError, match="unreadable"):
        artifacts.load_coverage(tmp_path)


def test_radon_blocks_with_no_targets_is_empty(tmp_path: Path) -> None:
    assert artifacts.radon_blocks(_ctx(tmp_path, changed=[])) == {}


def test_radon_blocks_parses_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(artifacts, "run_cmd", lambda *a, **k: _proc(stdout='{"a.py": []}'))
    assert artifacts.radon_blocks(_ctx(tmp_path)) == {"a.py": []}


def test_radon_blocks_without_output_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(artifacts, "run_cmd", lambda *a, **k: _proc(stderr="radon exploded"))
    with pytest.raises(artifacts.ArtifactError, match="no output"):
        artifacts.radon_blocks(_ctx(tmp_path))


def test_radon_blocks_unparsable_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(artifacts, "run_cmd", lambda *a, **k: _proc(stdout="{not json"))
    with pytest.raises(artifacts.ArtifactError, match="unparsable"):
        artifacts.radon_blocks(_ctx(tmp_path))


def test_radon_symbol_qualifies_methods() -> None:
    assert artifacts.radon_symbol({"name": "m", "classname": "K"}) == "K.m"
    assert artifacts.radon_symbol({"name": "f"}) == "f"
