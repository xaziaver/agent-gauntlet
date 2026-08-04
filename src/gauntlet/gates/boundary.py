"""Boundary gate: step definitions may only reach the system through a test API.

Acceptance tests that import production internals directly overfit to the
implementation and rot with every refactor. A stable test API layer is what keeps
them describing behavior rather than structure.

This gate exists because the rule previously lived only in a prompt — and a rule
that lives in a prompt is exactly what this tool was built to replace.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "boundary"

DEFAULT_STEPS = "tests/steps"
DEFAULT_API = "tests/api"
THRESHOLD = "step definitions import only the test API"


def _importable_name(entry: Path) -> str | None:
    if entry.is_dir():
        return entry.name if (entry / "__init__.py").is_file() else None
    if entry.suffix == ".py" and entry.stem != "__init__":
        return entry.stem
    return None


def production_packages(src: Path) -> set[str]:
    """Top-level importable names in the source tree."""
    if not src.is_dir():
        return set()
    names = (_importable_name(entry) for entry in src.iterdir())
    return {name for name in names if name is not None}


def _from_import(node: ast.ImportFrom) -> list[tuple[str, int]]:
    """Absolute `from x import y` only; relative imports stay inside the test tree."""
    if node.level or not node.module:
        return []
    return [(node.module.split(".")[0], node.lineno)]


def _roots_from(node: ast.AST) -> list[tuple[str, int]]:
    if isinstance(node, ast.Import):
        return [(alias.name.split(".")[0], node.lineno) for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return _from_import(node)
    return []


def imported_roots(source: str, filename: str = "<string>") -> list[tuple[str, int]]:
    """(top-level module, line) for every absolute import.

    Unparsable source returns nothing: the static gate reports the syntax error
    loudly, and this gate should not report it a second time.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []
    return [root for node in ast.walk(tree) for root in _roots_from(node)]


def _diagnostic(rel: str, module: str, line: int, api: str) -> Diagnostic:
    return Diagnostic(
        file=rel,
        symbol=module,
        line=line,
        message=(
            f"Step definitions must not import production code directly: {module!r}. "
            f"Reach the system through {api}/ instead. A step bound to internals "
            f"describes the implementation rather than the behavior, and breaks on "
            f"every refactor."
        ),
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _file_diagnostics(path: Path, packages: set[str], root: Path, api: str) -> list[Diagnostic]:
    source = _read(path)
    if source is None:
        return []
    rel = str(path.relative_to(root))
    return [
        _diagnostic(rel, module, line, api)
        for module, line in imported_roots(source, rel)
        if module in packages
    ]


def judge(files: list[Path], packages: set[str], root: Path, api: str) -> list[Diagnostic]:
    """Pure: which step files reach past the test API."""
    diagnostics: list[Diagnostic] = []
    for path in files:
        diagnostics.extend(_file_diagnostics(path, packages, root, api))
    return diagnostics


def _vacuous(reason: str) -> GateResult:
    return GateResult(gate=name, passed=True, threshold=THRESHOLD, actual=reason, vacuous=True)


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    api = str(config.get("api", DEFAULT_API))
    steps_dir = ctx.project_root / str(config.get("steps", DEFAULT_STEPS))
    if not steps_dir.is_dir():
        return _vacuous(f"no step definitions at {steps_dir.name}")

    packages = production_packages(ctx.src)
    if not packages:
        return _vacuous("no source packages")

    files = sorted(steps_dir.rglob("*.py"))
    diagnostics = judge(files, packages, ctx.project_root, api)
    return GateResult(
        gate=name,
        passed=not diagnostics,
        threshold=THRESHOLD,
        actual=f"{len(files)} step file(s), {len(diagnostics)} direct import(s)",
        diagnostics=diagnostics,
    )
