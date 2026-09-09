# Architecture and conventions

For anyone — human or agent — picking this up cold. The README explains what Gauntlet does and why.
This explains how it is built, which decisions are load-bearing, and where the bodies are buried.

Read this before changing anything structural. Several things that look wrong are deliberate, and
the reasons are recorded here because they were expensive to learn.

---

## The shape of the thing

```
src/gauntlet/
├── cli.py               command definitions only — no logic
├── cli_support.py       shared plumbing: exit codes, config resolution, gate selection
├── cli_specs.py         gauntlet spec …
├── cli_mutants.py       gauntlet mutant …
├── cli_status.py        gauntlet status
├── cli_review.py        gauntlet review
├── cli_events.py        gauntlet events
├── cli_loop.py          gauntlet loop
├── cli_approvals.py     gauntlet lock / verify
│
├── config.py            gauntlet.toml -> Config; the canonical gate order
├── runner.py            gate registry, context construction, execution
├── report.py            GateResult[] -> human text or JSON
├── events.py            append-only event log
├── status.py            composition: gates + pending approvals + activity
├── status_render.py     human rendering for status
│
├── registry.py          the approval primitive: hash, approve, verify, statuses
├── locking.py           config approvals (namespace: config)
├── specs.py             spec approvals (namespace: spec)
├── mutants.py           equivalent-mutant approvals (namespace: mutant), generic
├── review.py            decision logic for the approval walk
├── guard.py             PreToolUse decision logic
├── stop.py              Stop-hook attempt tracking
├── loop.py              the external agent driver
├── scaffold.py          generated files: settings.json, CLAUDE.md, CI, config template
├── doctor.py            environment checks and advisory warnings
│
├── gates/               one module per gate, uniform interface
│   ├── base.py          GateResult, GateContext, run_cmd, the timed decorator
│   └── …
├── acceptance/          language-independent Gherkin pipeline
│   ├── gherkin.py       text -> IR, with positions
│   └── mutation.py      IR -> mutants, and applying them
└── adapters/            the only language-specific code
    ├── base.py          RunResult, the adapter protocol
    └── python.py        pytest, pytest-bdd, mutmut, interpreter resolution
```

The layering rule: **`gates/` and `acceptance/` never import from `adapters/` except through the
gate that needs it, and `acceptance/` never imports `adapters/` at all.** That boundary is what
makes a second language a matter of adding one module rather than editing twelve.

---

## Contracts you must not break

### Exit codes

```
0  passed
1  gauntlet could not run (bad config, unknown gate, malformed payload)
2  gates failed
```

The 1/2 split is not cosmetic. Claude Code treats **exit 2 as blocking and exit 1 as a non-blocking
error it ignores.** So a config typo fails open — the agent is not wedged — and a real gate failure
blocks. Never conflate them, and never return 1 for a gate failure "because something went wrong."

### `GateResult`

Every gate returns one. Four fields carry meaning beyond the obvious:

- **`error`** is separate from `passed` because "the tool crashed" and "the gate legitimately
  failed" demand different agent behavior. A crashed tool must never read as a clean bill of health
  — this bug has appeared three times (mypy absent, ruff missing, jscpd absent) and each time it
  silently disabled a gate.
- **`vacuous`** means it passed because there was nothing to check. Silent under-enforcement is the
  most dangerous failure mode this tool has, and a gate that cannot say "I had no input" is a gate
  that lies by omission.
- **`diagnostics`** are prescriptive. Every message names the file, the symbol, the line, and **the
  remedy**. A capable model infers the fix from the measurement; a small one does not, and small
  models are half the audience.
- **`threshold` and `actual`** are rendered to humans and agents both. Keep them small and
  JSON-serializable.

### The JSON report

Flat, stable, boring. Agents parse it. Diagnostics are sorted worst-first and capped by
`max_diagnostics_per_gate`, with `diagnostics_truncated` reporting what was hidden — because Claude
Code truncates hook output at 10,000 characters and an honest cap beats a silent one.

### The event log

Append-only JSONL at `.gauntlet/events.jsonl`. Envelope fields (`v`, `at`, `run`, `kind`) are
written **last** so a payload key can never shadow them. Writing an event must never raise: a lost
line beats a broken gate.

---

## Conventions

### Pure logic, thin `run()`

Every gate splits into pure functions (parse, judge) and a thin `run()` that does subprocess work
and assembles a `GateResult`. This is not style — it is what makes the logic testable against canned
tool output with no mocking, and it was forced on the project by its own complexity gate.

When you add a gate, write the parser and the judge first, with table-driven tests, then wire the
subprocess.

### Never trust a tool's silence

Check return codes. `ruff` exits 0 clean / 1 with findings; anything else is a failure. `mypy` exits
1 both for "errors found" (with output) and "not installed" (without) — silence plus nonzero is a
broken tool, not a pass. `mutmut results` lists **only unkilled mutants**, so the killed count comes
from the run total, never from counting lines.

### `run_cmd` is the only subprocess entry point

It converts timeouts (124) and missing executables (127) into normal results rather than exceptions,
because an uncaught exception in a hook exits 1 and fails open.

### The interpreter question

Gauntlet supplies ruff, mypy, and radon and runs them with **its own** interpreter. The project
supplies pytest, pytest-cov, pytest-bdd, and mutmut, which run with **the project's** interpreter,
resolved by `adapters.python.interpreter()`. mypy bridges the two with `--python-executable`.

`interpreter()` deliberately does **not** resolve symlinks: `.venv/bin/python` is a symlink to the
base interpreter, and resolving it yields a Python without the venv's packages. That bug cost an
afternoon.

### One ledger, namespaced

All human approvals live in `gauntlet.lock.json` under `config:`, `spec:`, and `mutant:` prefixes.
One file to protect, one diff to review, one lifecycle: **propose → review → hash → auto-invalidate
on change.**

Two rules every consumer inherits, both learned the hard way:

- The ledger file must itself be a protected path, or an agent approves its own work.
- `MODIFIED` must stay distinct from `UNAPPROVED`, and both from `ABSENT`. Conflating them turns
  approval into a rubber stamp, or makes a path a project simply does not have look like a
  violation.

Approvals are keyed on a **structural locator** (scenario + kind + surrounding row), never on line
numbers. Insert a scenario above and every line-keyed approval would silently lapse.

### Gates are never interactive; review is

Gates do not prompt, do not read stdin (except the hook commands, which take a payload), and behave
identically under a terminal, a hook, and CI. A gate whose verdict depends on who ran it is not a
gate.

`gauntlet review` is deliberately conversational — it is a thing a person chooses to run. That split
is the design, not an inconsistency.

### Diagnostics offer an escape valve

The guard's refusal ends with *"if you believe a threshold is genuinely wrong, say so and let the
human decide."* A model facing an impossible requirement with no way out can only thrash. In
testing, an agent used this to argue — correctly — against a change the human had requested.

---

## How to add a gate

1. `src/gauntlet/gates/<name>.py` with `name = "<name>"` and `run(ctx, config) -> GateResult`.
2. Pure `parse`/`judge` functions first; tests against canned output; `run()` last.
3. Add the name to `DEFAULT_GATE_ORDER` in `config.py` — position matters, cheapest first, so an
   agent fixes syntax before it is shown a coverage number.
4. Add the module to `REGISTRY` in `runner.py`.
5. If it shells out to a tool, add it to `doctor.py`'s `CHECK_ORDER` and `GATES_BY_TOOL`, and decide
   whether it runs under Gauntlet's interpreter or the project's.
6. Add the config block to `scaffold.GAUNTLET_TOML_TEMPLATE`, commented out if it needs a
   dependency.
7. Handle the empty-input case with `vacuous=True`.

## How to add a language adapter

1. `src/gauntlet/adapters/<lang>.py` implementing the same functions `python.py` does:
   `interpreter`, `run_acceptance`, and the mutation entry points.
2. Nothing in `acceptance/` should change — the Gherkin IR and the mutation engine are language
   independent by construction, which is the whole point of that split.
3. Gates dispatch on `cfg.language`. That dispatch does not exist yet; adding it is part of the work
   and should be a lookup table, not a chain of conditionals.

---

## Testing conventions

- **Pure functions get table-driven unit tests** against canned tool output. Copy real output into
  the test file; do not invent a format.
- **Gates get integration tests** against a real temporary project. `tests/test_gate_runs.py` is the
  pattern.
- **Subprocess behavior is faked at `run_cmd`**, not at the library boundary, so tests exercise the
  real parsing path.
- **Assert on the property, not the phrasing.** Several tests have broken on message rewording;
  assert that a remedy is present, not its exact words.
- **Every test name is a sentence about behavior.** `test_an_empty_suite_fails_rather_than_passing_vacuously`
  is worth more than `test_run_5`.

The suite takes about a minute, mostly from integration tests that spawn real pytest runs. That is
deliberate and worth the cost — those tests have caught things no unit test could.

---

## Things that look wrong but are deliberate

- **The tests gate fails on an empty suite.** Otherwise deleting the test directory is a valid way
  to go green.
- **The coverage gate emits diagnostics only for enforced rules.** With `per_file_min` unset it says
  nothing about individual files, so a passing gate never emits guidance an agent could mistake for
  a failure.
- **The protect gate fails open when there is no lock file.** Installing Gauntlet must not
  immediately break a project. `require_lock = true` is the opt-in.
- **`init` does not approve what it generates.** It writes `.claude/settings.json`, which is a
  verified path, and then tells you to run `gauntlet lock`. Self-approval would defeat the purpose.
- **Stale approvals report but do not fail.** A judgment that no longer applies is housekeeping, not
  a defect.
- **Mutation defaults to `require_review = false`** while acceptance mutation effectively requires
  review. Unit-test mutants number in the hundreds; acceptance mutants number in the dozens and each
  one means something.

---

## Known sharp edges

- **mutmut** copies the source tree with a plain `copy2` and dies on a dangling symlink — an Emacs
  lock file is exactly that. It also leaves a `mutants/` directory that collides with pytest
  collection. `doctor` warns about both.
- **A copied project directory is broken** until `.venv` and `__pycache__` are removed and rebuilt;
  both embed absolute paths, and the symptom is import errors naming the *original* path.
- **Acceptance mutation is expensive** — one full suite run per mutant. `mutation_sample` and
  `scope = "changed"` exist for this reason.
- **`gauntlet.toml` edits require `gauntlet lock`** before the next check will pass. This surprises
  people constantly and is working as designed.

---

## Where to look next

`docs/GATES.md` explains each gate: why it exists, what it runs, how it decides, and the decisions
inside it that are easy to misread from the source.

`BACKLOG.md` holds known defects and planned work, each with the evidence that produced it. The
README's roadmap sketches versions. Between them they should answer "what should I work on" without
anyone having to reconstruct the reasoning.
