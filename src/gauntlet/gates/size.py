"""Size gate: function and module line limits, measured with the stdlib ast."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from gauntlet.gates.base import Diagnostic, GateContext, GateResult, timed

name = "size"


class _FunctionVisitor(ast.NodeVisitor):
    """Collects (qualified_name, lineno, line_count) for every function and method."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.found: list[tuple[str, int, int]] = []

    def _descend(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = ".".join([*self.stack, node.name])
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        self.found.append((qualname, node.lineno, length))
        self._descend(node, node.name)

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._descend(node, node.name)


def _function_lengths(source: str, filename: str = "<string>") -> list[tuple[str, int, int]]:
    """(qualified_name, lineno, line_count) for every function and method.

    Returns nothing for source that will not parse: the static gate reports the
    syntax error loudly, so this gate should not crash on it.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []
    visitor = _FunctionVisitor()
    visitor.visit(tree)
    return visitor.found


def _read(path: Path) -> str | None:
    """Source text, or None if the file vanished or cannot be decoded."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _module_diagnostic(rel: str, module_lines: int, max_mod: int) -> Diagnostic | None:
    if module_lines <= max_mod:
        return None
    return Diagnostic(
        file=rel,
        value=module_lines,
        message=f"Module is {module_lines} lines (max {max_mod}). Split it into smaller modules.",
    )


def _function_diagnostic(
    rel: str, qualname: str, lineno: int, length: int, max_fn: int
) -> Diagnostic:
    return Diagnostic(
        file=rel,
        symbol=qualname,
        line=lineno,
        value=length,
        message=f"{qualname} is {length} lines (max {max_fn}). Extract helper functions.",
    )


def _judge_file(rel: str, source: str, max_fn: int, max_mod: int) -> tuple[int, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    module_diag = _module_diagnostic(rel, len(source.splitlines()), max_mod)
    if module_diag is not None:
        diagnostics.append(module_diag)
    worst = 0
    for qualname, lineno, length in _function_lengths(source, rel):
        worst = max(worst, length)
        if length > max_fn:
            diagnostics.append(_function_diagnostic(rel, qualname, lineno, length, max_fn))
    return worst, diagnostics


@timed
def run(ctx: GateContext, config: dict[str, Any]) -> GateResult:
    max_fn = int(config.get("max_function_lines", 25))
    max_mod = int(config.get("max_module_lines", 300))

    diagnostics: list[Diagnostic] = []
    worst = 0
    for path in ctx.python_files():
        source = _read(path)
        if source is None:
            continue
        file_worst, file_diags = _judge_file(
            str(path.relative_to(ctx.project_root)), source, max_fn, max_mod
        )
        worst = max(worst, file_worst)
        diagnostics.extend(file_diags)

    return GateResult(
        gate=name,
        passed=not diagnostics,
        threshold={"max_function_lines": max_fn, "max_module_lines": max_mod},
        actual={"worst_function_lines": worst},
        diagnostics=diagnostics,
    )
