"""Loads and validates gauntlet.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "gauntlet.toml"
REQUIRED_PROJECT_KEYS = ("language", "src", "tests")

# Execution order: cheap and structural first, so an agent fixes syntax and shape
# before it is ever shown a coverage number. Later phases append "crap",
# "duplication", "mutation", "acceptance" to the end.
DEFAULT_GATE_ORDER = ["static", "size", "complexity", "tests", "coverage"]


class ConfigError(Exception):
    """Gauntlet cannot be configured. Maps to exit code 1, never 2."""


@dataclass(frozen=True)
class Config:
    language: str
    src: Path
    tests: Path
    gates: dict[str, dict[str, Any]]
    output: dict[str, Any]

    @property
    def enabled_gates(self) -> list[str]:
        return [g for g in DEFAULT_GATE_ORDER if g in self.gates]

    @property
    def max_diagnostics(self) -> int:
        return int(self.output.get("max_diagnostics_per_gate", 10))


def find_root(start: Path | None = None) -> Path:
    """Nearest ancestor directory containing gauntlet.toml.

    Searching upward means gauntlet works from any subdirectory — which matters
    for agent hooks, whose working directory is not guaranteed.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / CONFIG_FILENAME).exists():
            return candidate
    raise ConfigError(
        f"No {CONFIG_FILENAME} found in {current} or any parent directory. "
        f"Run `gauntlet init` first."
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"No {CONFIG_FILENAME} in {path.parent}.") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from None


def _validated_project(raw: dict[str, Any], path: Path) -> dict[str, Any]:
    project = raw.get("project")
    if not isinstance(project, dict):
        raise ConfigError(f"{path} is missing the [project] table.")
    missing = sorted(set(REQUIRED_PROJECT_KEYS) - set(project))
    if missing:
        raise ConfigError(f"{path} is missing [project] key(s): {missing}")
    unknown = sorted(set(raw.get("gates", {})) - set(DEFAULT_GATE_ORDER))
    if unknown:
        raise ConfigError(f"Unknown gate(s) in {path}: {unknown}. Known: {DEFAULT_GATE_ORDER}")
    return project


def load(project_root: Path) -> Config:
    path = project_root / CONFIG_FILENAME
    raw = _read_toml(path)
    project = _validated_project(raw, path)
    return Config(
        language=project["language"],
        src=(project_root / project["src"]).resolve(),
        tests=(project_root / project["tests"]).resolve(),
        gates=raw.get("gates", {}),
        output=raw.get("output", {}),
    )
