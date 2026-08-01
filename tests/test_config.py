from pathlib import Path

import pytest

from gauntlet import config as config_mod

VALID = """
[project]
language = "python"
src = "src/"
tests = "tests/"

[output]
max_diagnostics_per_gate = 3

[gates.coverage]
line = 80

[gates.static]
"""


def _project(tmp_path: Path, text: str = VALID) -> Path:
    (tmp_path / "gauntlet.toml").write_text(text)
    return tmp_path


def test_load_resolves_paths_against_the_root(tmp_path: Path) -> None:
    cfg = config_mod.load(_project(tmp_path))
    assert cfg.language == "python"
    assert cfg.src == (tmp_path / "src").resolve()
    assert cfg.tests == (tmp_path / "tests").resolve()


def test_enabled_gates_follow_canonical_order_not_file_order(tmp_path: Path) -> None:
    cfg = config_mod.load(_project(tmp_path))
    assert cfg.enabled_gates == ["static", "coverage"]


def test_max_diagnostics_reads_output_table(tmp_path: Path) -> None:
    assert config_mod.load(_project(tmp_path)).max_diagnostics == 3


def test_max_diagnostics_defaults_when_absent(tmp_path: Path) -> None:
    text = VALID.replace("[output]\nmax_diagnostics_per_gate = 3\n", "")
    assert config_mod.load(_project(tmp_path, text)).max_diagnostics == 10


def test_missing_project_table_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(config_mod.ConfigError, match=r"\[project\] table"):
        config_mod.load(_project(tmp_path, "[gates.static]\n"))


def test_missing_required_key_names_the_key(tmp_path: Path) -> None:
    text = '[project]\nlanguage = "python"\nsrc = "src/"\n'
    with pytest.raises(config_mod.ConfigError, match="tests"):
        config_mod.load(_project(tmp_path, text))


def test_unknown_gate_is_rejected_loudly(tmp_path: Path) -> None:
    """An agent 'disabling' a gate by typo must fail, not silently skip it."""
    with pytest.raises(config_mod.ConfigError, match="mutaton"):
        config_mod.load(_project(tmp_path, VALID + "\n[gates.mutaton]\n"))


def test_invalid_toml_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(config_mod.ConfigError, match="not valid TOML"):
        config_mod.load(_project(tmp_path, "[project\n"))


def test_find_root_searches_upward(tmp_path: Path) -> None:
    root = _project(tmp_path)
    nested = root / "src" / "pkg" / "deep"
    nested.mkdir(parents=True)
    assert config_mod.find_root(nested) == root.resolve()


def test_find_root_raises_when_no_config_anywhere(tmp_path: Path) -> None:
    with pytest.raises(config_mod.ConfigError, match="or any parent"):
        config_mod.find_root(tmp_path)


def test_python_is_optional(tmp_path: Path) -> None:
    assert config_mod.load(_project(tmp_path)).python is None
