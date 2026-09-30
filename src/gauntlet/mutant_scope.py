"""Which acceptance survivors an approval names: the scope of `gauntlet mutant approve`.

Pure selection over survivors already measured. `--scenario` narrows first, then
`--locator`; a locator that names no survivor is a mistake, never a vacuous
approval. An approval whose survivors span more than one scenario is the sweep
that `--all-scenarios` has to ask for by name.
"""

from __future__ import annotations

from gauntlet.acceptance.mutation import Mutant


class ScopeError(Exception):
    """A locator that no survivor in scope carries; the message is that locator."""


def _first_missing(known: set[str], wanted: list[str]) -> str | None:
    return next((name for name in wanted if name not in known), None)


def by_locator(survivors: list[Mutant], locators: list[str]) -> list[Mutant]:
    """The survivors at the named locators, or all of them when none is named."""
    if not locators:
        return survivors
    missing = _first_missing({m.locator for m in survivors}, locators)
    if missing is not None:
        raise ScopeError(missing)
    return [m for m in survivors if m.locator in locators]


def in_scope(survivors: list[Mutant], scenario: str, locators: list[str]) -> list[Mutant]:
    """`--scenario`, then `--locator`, over the survivors one feature has now."""
    scoped = [m for m in survivors if m.scenario == scenario] if scenario else survivors
    return by_locator(scoped, locators)


def swept(written: list[Mutant]) -> list[str]:
    """The scenarios an approval would write into, when there is more than one."""
    scenarios = list(dict.fromkeys(m.scenario for m in written))
    return scenarios if len(scenarios) > 1 else []
