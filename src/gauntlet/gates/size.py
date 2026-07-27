def _function_lengths(source: str, filename: str = "<string>") -> list[tuple[str, int, int]]:
    """(qualified_name, lineno, line_count) for every function/method."""
    tree = ast.parse(source, filename=filename)
    ...  # body unchanged


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def _judge_file(rel: str, source: str, max_fn: int, max_mod: int) -> tuple[int, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    module_lines = len(source.splitlines())
    if module_lines > max_mod:
        diagnostics.append(
            Diagnostic(file=rel, value=module_lines,
                       message=f"Module is {module_lines} lines (max {max_mod}). "
                               f"Split it into smaller modules.")
        )
    worst = 0
    for qualname, lineno, length in _function_lengths(source, rel):
        worst = max(worst, length)
        if length > max_fn:
            diagnostics.append(
                Diagnostic(file=rel, symbol=qualname, line=lineno, value=length,
                           message=f"{qualname} is {length} lines (max {max_fn}). "
                                   f"Extract helper functions.")
            )
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
        file_worst, file_diags = _judge_file(str(path.relative_to(ctx.project_root)),
                                             source, max_fn, max_mod)
        worst = max(worst, file_worst)
        diagnostics.extend(file_diags)

    return GateResult(
        gate=name, passed=not diagnostics,
        threshold={"max_function_lines": max_fn, "max_module_lines": max_mod},
        actual={"worst_function_lines": worst}, diagnostics=diagnostics,
    )
