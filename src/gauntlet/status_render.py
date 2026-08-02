"""Human rendering for `gauntlet status`."""

from __future__ import annotations

from typing import Any

from gauntlet.gates.base import GateResult
from gauntlet.report import FAIL, PASS
from gauntlet.status import Status

BULLET = "  •"

MAX_DETAIL = 70
SPINNER_CHARS = "⠁⠂⠃⠄⠅⠆⠇⠈⠉⠊⠋⠌⠍⠎⠏⠐⠑⠒⠓⠔⠕⠖⠗⠘⠙⠚⠛⠜⠝⠞⠟⠠⠡⠢⠣⠤⠥⠦⠧⠨⠩⠪⠫⠬⠭⠮⠯⠰⠱⠲⠳⠴⠵⠶⠷⠸⠹⠺⠻⠼⠽⠾⠿"


def _first_meaningful_line(text: str) -> str:
    """Tools write progress spinners to the same stream as their errors.

    A line beginning with a braille spinner is an in-place progress redraw, not
    a message — skip the lot and return the first real line.
    """
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned and cleaned[0] not in SPINNER_CHARS:
            return cleaned
    return text.strip()[:MAX_DETAIL]


def _detail(gate: GateResult) -> str:
    """One short line per gate. Full detail belongs in `gauntlet check`."""
    if gate.error:
        return f"ERROR: {_first_meaningful_line(gate.error)[:MAX_DETAIL]}"
    if isinstance(gate.actual, dict):
        return ", ".join(f"{key}={value}" for key, value in gate.actual.items())
    return str(gate.actual)[:MAX_DETAIL]


def _gate_lines(status: Status) -> list[str]:
    if not status.gates:
        return ["GATES     not run (use `gauntlet status --run`)"]
    verdict = "PASSING" if status.passed else "FAILING"
    lines = [f"GATES     {verdict}"]
    for gate in status.gates:
        mark = PASS if gate.passed else FAIL
        lines.append(f"{BULLET} {mark} {gate.gate:<12} {_detail(gate)}")
    if not status.passed:
        lines.append("      -> run `gauntlet check` for full diagnostics")
    return lines


def _pending_lines(status: Status) -> list[str]:
    if not status.pending:
        return ["WAITING   nothing needs your approval"]
    lines = [f"WAITING   {len(status.pending)} item(s) need your approval"]
    for item in status.pending:
        lines.append(f"{BULLET} {item.status:<11} {item.subject}")
        lines.append(f"      -> {item.action}")
    return lines


def _event_line(item: dict[str, Any]) -> str:
    detail = item.get("gate") or item.get("path") or item.get("subject") or ""
    if "passed" in item:
        detail = f"{PASS if item['passed'] else FAIL} {detail}"
    return f"{BULLET} {item.get('at', '?')}  {item.get('kind', '?'):<17} {detail}"


def _recent_lines(status: Status) -> list[str]:
    if not status.recent:
        return ["ACTIVITY  no recorded activity yet"]
    return ["ACTIVITY  most recent first", *[_event_line(i) for i in reversed(status.recent)]]


def render(status: Status) -> str:
    header = [f"PROJECT   {status.root}", f"LOCKED    {'yes' if status.locked else 'no'}", ""]
    sections = [_gate_lines(status), _pending_lines(status), _recent_lines(status)]
    lines = list(header)
    for section in sections:
        lines.extend([*section, ""])
    return "\n".join(lines).rstrip() + "\n"
