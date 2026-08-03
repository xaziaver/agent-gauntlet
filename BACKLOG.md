# Gauntlet — Backlog

Fixes and design adjustments, with the evidence that produced them. Everything here came from
building something real with the tool rather than from testing the tool itself.

Sources: the Gauntlet build, the `gauntlet-demo1` walkthrough, and phase 1 of ClaimGate (an FNOL
intake service built by Claude Code under the gates, August 2026).

---

## P1 — Highest value

### 1. Acceptance mutation picks alternatives that cannot discriminate

**Evidence.** ClaimGate's first full acceptance run produced **41 surviving mutants, all 41
equivalent.** Zero real findings, 94 seconds spent, and 41 human approvals required.

**Cause.** `mutate_value` swaps a cell for another value from the same column. Example tables
deliberately contain multiple rows mapping to the same outcome, so the swap usually lands on a row
with the same expected result:

```
| HO-1234567 | valid |     HO-1234567 -> AU-1234567 : still valid.  Survives.
| AU-1234567 | valid |     HO-1234567 -> XX-1234567 : now invalid.  Dies.
| XX-1234567 | invalid |
```

**Fix.** When choosing an alternative, prefer one drawn from a row whose *other* columns differ —
in practice, a row with a different expected outcome. Rough estimate: this alone would have killed
around 30 of ClaimGate's 41 survivors.

**Watch for.** The gate does not know which column is the "expected outcome"; inferring it (last
column? the one referenced by a `Then` step?) is the hard part. A simpler heuristic — prefer a value
from the most-different row by Hamming distance across the other columns — may get most of the
benefit without needing to know.

### 2. The tool cannot tell you what it is not doing

**Evidence.** Three separate incidents, months apart, same shape:

- ClaimGate ran with **7 of 10 gates** for an entire implementation phase. `check` and `status` list
  only what ran, so three commented-out tables were invisible. Discovered by noticing that a
  displayed threshold was the built-in default rather than the configured one.
- The first demo session ran with **both hooks dead** (exit 1, fail-open). The session looked
  perfect and the agent reported that all gates passed.
- `mypy` absent once parsed as **"no findings"** and passed the static gate.

**Fix.** A general principle, applied in three places:

- `status` and `doctor` report configured-but-inactive gates: *"3 available gates not enabled:
  duplication, mutation, acceptance."* It is a set difference over `DEFAULT_GATE_ORDER`.
- Gates that pass **vacuously** say so distinctly rather than reporting success: acceptance with no
  feature files, mutation with no changed modules, any gate under `--changed` with nothing changed.
  A `vacuous: true` flag on `GateResult` would let the renderer mark them.
- `doctor` verifies the hook path end to end — that `gauntlet` on `PATH` is the same version, and
  that its environment can run every enabled gate.

### 3. Gates report downstream symptoms instead of upstream causes

**Evidence.** A brand-new project fails `gauntlet check` immediately after `gauntlet init` with
three errors, none of which name the actual problem (an empty `src/`):

```
✗ static    ERROR: mypy exited 2: There are no .py[i] files in directory '.../src'
✗ coverage  ERROR: No .gauntlet/coverage.json — the tests gate must run before this gate
✗ crap      ERROR: No .gauntlet/coverage.json — the tests gate must run before this gate
```

The coverage message is actively misleading: the tests gate *did* run.

**Fix.**

- Gates check their own preconditions first and say so plainly: "no Python files under `src/`".
- Coverage distinguishes "the tests gate did not run" from "the tests gate ran and produced no
  data".
- `init` scaffolds a package `__init__.py`, one trivial module, and one test, so a new project is
  green by construction.

---

## P2 — Real gaps

### 4. The test API boundary gate was designed and never built

Step definitions should only reach the system through a stable `tests/api/` layer, checked with an
AST pass over imports. It was point 5 of the Phase 4 build order, the config key was written into
the template, and the gate was never implemented. The key has since been removed.

This matters more than a missing feature: test/production separation is one of the practices the
whole methodology rests on, and right now it can only live in a prompt — which is precisely the
decay this project exists to prevent. ClaimGate's kickoff prompt asks for the boundary and nothing
enforces it.

### 5. Mutation cost is unmanaged

**Evidence.** Acceptance mutation on four small feature files: **94 seconds**, on every `Stop` hook.
Code mutation on this repository's own source: **87 minutes** for 3,752 mutants, because its tests
spawn subprocesses. ClaimGate's domain package: 3 seconds for 109, because its tests are pure.

**Fix.**

- Default `mutation_sample` to a non-zero value for the acceptance gate rather than "all", and
  document `scope = "changed"` as mandatory rather than merely default.
- Report elapsed mutation time in the gate's `actual`, so the cost is visible before it becomes
  painful.
- Consider caching: a mutant whose locator and signature are unchanged since the last green run,
  against unchanged bindings, does not need re-running.

### 6. mutmut is fragile in a working tree

It copies the source tree with a plain `copy2`, which dies on a dangling symlink — an Emacs lock
file is exactly that. It also leaves a `mutants/` directory that collides with pytest collection.
Both now produce a `doctor` warning and a translated gate error, but the underlying fragility is
inherited and worth documenting prominently rather than patching around.

### 7. A copied project directory is silently broken

Virtualenvs and `__pycache__` embed absolute paths, so a copied directory fails with import errors
naming the *original* path. Cost roughly twenty minutes to diagnose on `gauntlet-demo1`. A `doctor`
check — does any `__pycache__` reference a path outside this project — would turn it into a
sentence, though the detection is a little speculative.

---

## P3 — Design adjustments worth considering

### 8. Warn when a spec asserts on a value it was given

ClaimGate's queue-routing scenario takes `severity` as a `Given` and asserts it as a `Then`.
Mutating that cell changes the input and the expectation together, so it is structurally unkillable
— and the scenario tests less than it appears to. A cheap lint: flag any Example column referenced
by both a `Given` and a `Then` step in the same scenario.

### 9. Money, floats, and boundary thresholds

Not a Gauntlet defect, but a recurring hazard: `499.99 + 0.01 != 500.00` in binary floating point,
and mutation testing will eventually find it. Worth a line in the generated `CLAUDE.md` block —
monetary amounts use `Decimal` — since the gates cannot detect the class of bug directly.

### 10. Per-file coverage is noisy on framework code

`per_file_min` works well on a pure domain package and poorly on route handlers and adapters full of
framework boilerplate. Consider per-directory thresholds, or document the pattern: strict on the
domain, aggregate-only elsewhere.

---

## Confirmed working — do not regress

Evidence that the core ideas hold, kept so that refactors have something to preserve.

**Code mutation finds real bugs that coverage cannot.** ClaimGate had 122 tests and 100% line and
branch coverage. Mutation found two genuine gaps: an untested `None` branch in the inception check,
and an `or`/`and` guard where a non-theft loss with an amount under $500 would have been misclassified
as low severity. Neither was reachable through coverage.

**Mutation testing finds untested boundaries.** On the demo project it identified four thresholds
where no test used the exact boundary value — 50,000, 90 days, 1,000 — all hidden behind 100%
coverage.

**The equivalent-mutant ledger works.** Classify once, with a reason and a reviewer; the judgment
persists and lapses automatically when the surrounding case changes. Used in anger on both projects.

**The protect gate catches real drift**, including changes made by routes the guard cannot see. The
`review` walk showing a diff before approval is what makes the approval meaningful.

**Advisory context does help capable models.** ClaimGate's agent ran `gauntlet check` itself 22
times across the session, unprompted after the first, and never attempted to weaken a threshold.
That is not enforcement and should never be relied upon — but it is real, and cheap.

**The spec-change loop is sound.** The human requests a spec change, the agent edits, the gate
reports the spec as modified, and the human re-approves. That happened on ClaimGate and worked
exactly as designed.

---

## Open questions

- **Did the ClaimGate hooks actually fire?** The session shows no blocking hook output at all. That
  is consistent with an agent whose code always passed the fast gates (max function 10 lines, max
  complexity 5) — but it is also consistent with dead hooks, and there is no way to tell after the
  fact. That ambiguity is itself the argument for item 2.
- **Is acceptance mutation worth its cost once item 1 is fixed?** It proved the bindings were
  connected, which is real. But on this evidence its signal-to-noise is far worse than code
  mutation's, and the honest answer may be that it belongs in CI rather than in the edit loop.
