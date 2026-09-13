"""Which step modules bind a feature file.

Discovered on every call from the `scenarios(...)` and `scenario(...)` calls in
the step files, never cached in memory or on disk: a cached map goes stale the
moment a step file is edited, and rereading costs one `ast.parse` per module.
Pure — no config, no ledger, no state — so it is usable as a plain library.
"""

from __future__ import annotations

import ast
from pathlib import Path

BINDING_CALLS = frozenset({"scenarios", "scenario"})


def _callee(node: ast.Call) -> str:
    """`scenarios(...)` and `pytest_bdd.scenarios(...)` both name `scenarios`."""
    return str(getattr(node.func, "attr", None) or getattr(node.func, "id", ""))


def _first_literal(node: ast.Call) -> str | None:
    """The call's first argument when it is a string literal; a computed path binds nothing."""
    first = node.args[0] if node.args else None
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _literal_targets(tree: ast.AST) -> list[str]:
    """The first argument of every binding call, where it is a string literal."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee(node) in BINDING_CALLS:
            target = _first_literal(node)
            if target is not None:
                found.append(target)
    return found


def bound_targets(module: Path) -> list[Path]:
    """Every path a step module binds, resolved against the module's own directory.

    A file that cannot be read as UTF-8 or parsed binds nothing rather than
    raising: pytest never collects it, and nothing between a gate and the exit
    code catches an exception, so a raise here would fail the Stop hook open.
    """
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"), str(module))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return [(module.parent / target).resolve() for target in _literal_targets(tree)]


def _binds(target: Path, feature: Path) -> bool:
    """A file target binds that feature; a directory target binds every feature beneath it."""
    return target == feature or (target.is_dir() and feature.is_relative_to(target))


def bound_modules(steps: Path, feature: Path) -> list[Path]:
    """The step modules under `steps` that bind `feature`, sorted. Reread every call."""
    resolved = feature.resolve()
    return sorted(
        module
        for module in steps.rglob("*.py")
        if any(_binds(target, resolved) for target in bound_targets(module))
    )
