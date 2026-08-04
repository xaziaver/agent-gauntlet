"""Environment checks: is every enabled gate actually able to run?

Hooks fail open by design — a broken Gauntlet exits 1, Claude Code shrugs, and
enforcement silently disappears while the session looks normal. This is the
command that makes that state visible.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gauntlet import __version__

SETTINGS_PATH = Path(".claude") / "settings.json"

CHECK_ORDER = (
    "git",
    "ruff",
    "mypy",
    "radon",
    "pytest",
    "pytest-cov",
    "pytest-bdd",
    "mutmut",
    "jscpd",
)

# Which gates need which tool. Gates absent here need only the standard library.
GATES_BY_TOOL = {
    "git": ("--changed",),
    "ruff": ("static",),
    "mypy": ("static",),
    "radon": ("complexity", "crap"),
    "pytest": ("tests",),
    "pytest-cov": ("coverage", "crap"),
    "pytest-bdd": ("acceptance",),
    "mutmut": ("mutation",),
    "jscpd": ("duplication",),
}

PROJECT_MODULES = {
    "pytest": "pytest",
    "pytest-cov": "pytest_cov",
    "pytest-bdd": "pytest_bdd",
    "mutmut": "mutmut",
}

OWN_MODULES = {"mypy": "mypy"}

EDITOR_ARTIFACT_GLOBS = (".#*", "#*#", "*~")


@dataclass(frozen=True)
class Check:
    tool: str
    ok: bool
    detail: str

    @property
    def gates(self) -> tuple[str, ...]:
        return GATES_BY_TOOL[self.tool]


def _on_path(executable: str) -> Check:
    found = shutil.which(executable)
    detail = found or "not on PATH — gates depending on it will error, not pass"
    return Check(tool=executable, ok=found is not None, detail=detail)


def _importable_by(tool: str, module: str, python: str) -> Check:
    proc = subprocess.run(
        [python, "-c", f"import {module}"], capture_output=True, text=True, check=False
    )
    detail = (
        f"importable by {python}"
        if proc.returncode == 0
        else (f"module {module!r} not importable by {python}")
    )
    return Check(tool=tool, ok=proc.returncode == 0, detail=detail)


def _check_for(tool: str, python: str) -> Check:
    if tool in PROJECT_MODULES:
        return _importable_by(tool, PROJECT_MODULES[tool], python)
    if tool in OWN_MODULES:
        return _importable_by(tool, OWN_MODULES[tool], sys.executable)
    return _on_path(tool)


def run_checks(enabled_gates: list[str], python: str | None = None) -> list[Check]:
    """One check per tool any enabled gate (or --changed) depends on."""
    resolved = python or sys.executable
    relevant = set(enabled_gates) | {"--changed"}
    return [
        _check_for(tool, resolved) for tool in CHECK_ORDER if relevant & set(GATES_BY_TOOL[tool])
    ]


def _check_lines(check: Check) -> list[str]:
    mark = "ok " if check.ok else "MISSING"
    lines = [f"{mark:<8} {check.tool:<11} needed by {', '.join(check.gates)}"]
    if not check.ok:
        lines.append(f"         {check.detail}")
    return lines


def _header(python: str | None) -> list[str]:
    return [
        f"gauntlet: {sys.argv[0]}",
        f"gauntlet python: {sys.executable}",
        f"project python:  {python or sys.executable}",
        "",
    ]


def render(
    checks: list[Check], python: str | None = None, warnings: list[str] | None = None
) -> str:
    lines = _header(python)
    for check in checks:
        lines.extend(_check_lines(check))
    lines.extend(f"\nWARNING  {warning}" for warning in warnings or [])
    return "\n".join(lines)


def healthy(checks: list[Check]) -> bool:
    return all(check.ok for check in checks)


def mutants_dir_warning(root: Path, enabled_gates: list[str]) -> str | None:
    """mutmut's ./mutants copy collides with the project's own test collection."""
    if "mutation" not in enabled_gates or not (root / "mutants").is_dir():
        return None
    config = root / "pyproject.toml"
    text = config.read_text(encoding="utf-8") if config.is_file() else ""
    if "--ignore=mutants" in text or "--ignore ./mutants" in text:
        return None
    return (
        "./mutants exists (created by mutmut) and pytest is not ignoring it. "
        'Add addopts = "--ignore=mutants" under [tool.pytest.ini_options], '
        "and put mutants/ in .gitignore."
    )


def warnings_for(
    root: Path, src: Path, enabled_gates: list[str], disabled_gates: list[str] | None = None
) -> list[str]:
    """Advisory environment problems: real, but not a missing tool."""
    found = [
        hook_warning(root),
        disabled_warning(disabled_gates or []),
        mutants_dir_warning(root, enabled_gates),
        editor_artifact_warning(src, enabled_gates),
    ]
    return [w for w in found if w is not None]


def _artifacts(src: Path) -> list[str]:
    found: list[str] = []
    for pattern in EDITOR_ARTIFACT_GLOBS:
        found.extend(str(path.relative_to(src)) for path in src.rglob(pattern))
    return sorted(found)


def editor_artifact_warning(src: Path, enabled_gates: list[str]) -> str | None:
    """mutmut copies the source tree with a plain copy2, which dies on a dangling
    symlink — and an Emacs lock file is exactly that."""
    if "mutation" not in enabled_gates or not src.is_dir():
        return None
    found = _artifacts(src)
    if not found:
        return None
    more = " ..." if len(found) > 3 else ""
    return (
        f"Editor lock/backup files under {src}: {', '.join(found[:3])}{more}. "
        f"mutmut cannot copy them and will fail. Close the file in your editor or "
        f"delete them."
    )


def _gauntlet_handlers(groups: Any) -> bool:
    """True when any handler in these matcher groups invokes gauntlet."""
    if not isinstance(groups, list):
        return False
    return any(
        handler.get("command") == "gauntlet"
        for group in groups
        if isinstance(group, dict)
        for handler in group.get("hooks", [])
    )


def _hook_commands(root: Path) -> set[str]:
    """Which hook events invoke gauntlet, per .claude/settings.json."""
    settings = root / SETTINGS_PATH
    if not settings.is_file():
        return set()
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, json.JSONDecodeError):
        return set()
    return {event for event, groups in hooks.items() if _gauntlet_handlers(groups)}


def _path_version() -> str | None:
    """The version of the `gauntlet` a hook would actually run."""
    found = shutil.which("gauntlet")
    if found is None:
        return None
    proc = subprocess.run([found, "version"], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def hook_warning(root: Path) -> str | None:
    """Hooks fail open, so a dead one is invisible. This is how you find out."""
    events = _hook_commands(root)
    if not events:
        return (
            "No Claude Code hooks are wired to gauntlet. Gates run only when you "
            "invoke them by hand. Run `gauntlet init --agent claude-code` to wire them."
        )
    on_path = _path_version()
    if on_path is None:
        return (
            "Hooks invoke bare `gauntlet`, which is not on PATH. Every hook will fail "
            "open and enforcement will be silently disabled. Install with "
            "`uv tool install --editable .`."
        )
    if on_path != __version__:
        return (
            f"Hooks would run gauntlet {on_path}, but this is {__version__}. Reinstall "
            f"with `uv tool install --reinstall --editable .`."
        )
    return None


def disabled_warning(disabled: list[str]) -> str | None:
    if not disabled:
        return None
    return (
        f"{len(disabled)} known gate(s) not enabled: {', '.join(disabled)}. "
        f"Add a [gates.<name>] table to gauntlet.toml to turn one on."
    )
