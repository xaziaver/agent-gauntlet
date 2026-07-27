# Gauntlet

**Don't review the agent's code — make it run the gauntlet.**

Gauntlet surrounds AI coding agents with deterministic, automated quality gates so a human can
manage quality from above instead of reading generated code line by line. Every standard becomes an
executable check with a threshold, a loud failure, and a machine-readable diagnostic the agent can
act on.

[![gauntlet](https://github.com/xaziaver/agent-gauntlet/actions/workflows/gauntlet.yml/badge.svg)](https://github.com/xaziaver/agent-gauntlet/actions/workflows/gauntlet.yml)

Gauntlet gates itself. Every commit in this repository has passed the seven gates below, measured by
this tool.

---

## Why

The method is Robert C. Martin's, stated plainly in mid-2026: he does not read the code his agents
write. Instead he surrounds them with constraints — unit tests, acceptance tests, coverage,
complexity limits, dependency rules, mutation testing — and manages quality through metrics rather
than review. The reasoning behind it is what makes it more than a slogan:

- **Rules written in prompts decay.** As a context window fills, instructions written in CLAUDE.md or
  a system prompt lose priority. A rule that lives in a tool with a threshold and an exit code does
  not decay.
- **Humans are slow at reading code.** The productivity gain from agents is only realized if the
  human disengages from the implementation and re-engages at the level of specifications and
  measurements.
- **Clean code still matters.** Agents get confused by tangled code the same way people do. The
  standards do not relax; the enforcement mechanism changes from inspection to automation.

Gauntlet is that enforcement mechanism, packaged as a CLI.

### Two audiences, one tool

A gate does different work depending on how capable the agent is:

- **For a weak model, the gates are a teacher.** A small model will not infer that a function should
  be extracted at cyclomatic complexity 7, or that a test asserting nothing is worthless. The gates
  supply the standard and the diagnostics supply the remedy.
- **For a strong model, the gates are an auditor.** Capable models often self-police to a high
  standard — and then report their own results. A frontier model finishing a session with "100%
  coverage, 131 of 133 mutants killed" is asking you to take its word for it. Gauntlet re-measures
  deterministically. Everything you know about the code comes from the tool, not from the agent.

---

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Manual spike: run the loop by hand | Done |
| 1 | CLI, config, report contract, five gates | Done |
| 2 | CRAP gate, duplication gate, shared artifacts | Done |
| 3 | `gauntlet init`, Claude Code hooks, protected paths | Planned |
| 3.5 | `gauntlet loop` — external driver for un-hookable agents | Planned |
| 4 | Gherkin acceptance pipeline, spec locking, acceptance mutation | Planned |
| 5 | Mutation testing gate | Planned |
| 6 | C# adapter | Planned |
| 7 | Docs and release polish | Planned |

Python projects only today. The adapter architecture exists for a second language target but has not
yet been exercised, which means it is a claim rather than a fact — see [Honest
limitations](#honest-limitations).

---

## Quick start

Requirements: Python 3.11+ (3.12 recommended), git. The duplication gate additionally needs Node.

```bash
# Install (from a clone, until this is published)
git clone https://github.com/xaziaver/agent-gauntlet
cd agent-gauntlet
uv sync

# Optional: the duplication gate
npm install -g jscpd
```

Create `gauntlet.toml` in your project root:

```toml
[project]
language = "python"
src = "src/"
tests = "tests/"

[output]
max_diagnostics_per_gate = 10

[gates.static]

[gates.size]
max_function_lines = 25
max_module_lines = 300

[gates.complexity]
max = 6

[gates.tests]

[gates.coverage]
line = 95
branch = 90
per_file_min = 80

[gates.crap]
max = 15

[gates.duplication]
max_duplicate_blocks = 0
```

Run it:

```bash
gauntlet check                                  # every configured gate
gauntlet check --gates static,size,complexity   # a subset
gauntlet check --changed                        # only files changed vs HEAD
gauntlet check --fail-fast                      # stop at the first failing gate
gauntlet check --json                           # machine-readable report
```

A gate table must be present in `gauntlet.toml` for that gate to run, even when empty
(`[gates.static]`). An unknown gate name in the config is a hard error, not a silent skip — an agent
should not be able to disable a gate with a typo.

---

## The gates

Gates run in a fixed order — cheap and structural first — so that an agent fixes syntax and shape
before it is ever shown a coverage number.

### 1. `static` — lint and type check

**Tool:** ruff + mypy.
**Measures:** every ruff rule enabled in your `pyproject.toml`, plus full mypy type checking.
**Fails when:** either tool reports anything.
**Does not measure:** anything about behavior. Clean static analysis says nothing about whether the
code is correct.

Diagnostics carry ruff's auto-fixability, so an agent is told when `ruff check --fix` resolves the
finding rather than being left to guess.

### 2. `size` — function and module length

**Tool:** the Python standard library `ast` module (no dependency).
**Measures:** physical line count of every function and method (qualified as `Class.method`), and of
every module.
**Fails when:** any function exceeds `max_function_lines` or any module exceeds `max_module_lines`.
**Does not measure:** whether the length is justified. A 30-line data table and a 30-line tangle of
branches fail identically.

Files that cannot be read or parsed are skipped rather than crashing the gate — agents create and
delete files constantly, and editor lock files (`.#name.py`) are dangling symlinks.

### 3. `complexity` — cyclomatic complexity

**Tool:** radon.
**Measures:** cyclomatic complexity per function and method.
**Fails when:** any function exceeds `max` (default 6, Uncle Bob's ceiling).
**Does not measure:** cognitive complexity, nesting depth, or coupling. A flat function with six
independent guard clauses scores the same as deeply nested branching.

The comparison is strictly greater-than, so a function exactly at the ceiling passes. Radon's letter
grades are ignored; a function at CC 6 is graded "B" by radon and still passes here.

### 4. `tests` — the suite must pass

**Tool:** pytest, via junitxml.
**Measures:** pass, fail, error, and skip counts; one diagnostic per failing test with the file,
line, failure headline, and the tail of the traceback.
**Fails when:** any test fails or errors, **or when no tests are collected at all**. An empty suite
is not a passing suite — otherwise deleting the test directory is a valid strategy for going green.
**Does not measure:** whether the tests are meaningful. A suite of `assert True` passes this gate.
That is what coverage, CRAP, and (in Phase 5) mutation testing are for.

This gate also produces the coverage artifact in the same run, so the suite executes once per
`gauntlet check` rather than once per gate.

### 5. `coverage` — line and branch coverage

**Tool:** coverage.py via pytest-cov, reading `.gauntlet/coverage.json`.
**Measures:** aggregate line coverage, aggregate branch coverage, and optionally per-file line
coverage.
**Fails when:** the aggregate falls below `line` or `branch`, or — when `per_file_min` is set — any
individual file falls below it.
**Does not measure:** assertion quality. Coverage counts lines executed, not behavior verified. A
test that calls a function and asserts nothing produces full coverage.

Diagnostics are emitted only for rules that are actually enforced: with `per_file_min` unset, the
gate judges the aggregate and stays silent about individual files, so a passing gate never emits
guidance an agent could mistake for a failure.

### 6. `crap` — Change Risk Anti-Pattern

**Tool:** computed, joining radon spans with coverage.py executed-line data.

```
CRAP = CC² × (1 − coverage)³ + CC
```

**Measures:** complexity and coverage *per function*, combined into one score.
**Fails when:** any function exceeds `max` (default 15).
**Does not measure:** anything the two inputs do not. It is a combination, not a new signal.

This gate exists for the case neither of its inputs catches: **a complex function that happens to sit
in a well-covered file.** The complexity gate sees CC 6 and passes it. The coverage gate sees a file
at 96% and passes it. CRAP sees a CC-6 function at 0% coverage and scores it 42.

The cubic term encodes the engineering judgment: at full coverage the penalty vanishes and CRAP
collapses to CC, so a well-tested complex function passes. At zero coverage complexity is punished
quadratically. That gives an agent a genuine choice rather than a single mandated remedy, and the
diagnostic states both options — the exact coverage percentage that would clear the ceiling, or
extraction. Above `CC == max`, no amount of testing helps and the diagnostic says so.

Per-function coverage is computed over *statements* in the function's line span, not physical lines;
blank lines and comments are not statements and counting them would understate coverage badly. Class
blocks are excluded because a class's complexity is the sum of its methods. A file that radon
analyzed but coverage did not is skipped rather than scored as zero, so a path-normalization bug
surfaces as a bug instead of silently failing the whole codebase.

### 7. `duplication` — copy-paste detection

**Tool:** jscpd (requires Node).
**Measures:** token-level clone detection across the source tree.
**Fails when:** the clone count exceeds `max_duplicate_blocks` (default 0).
**Does not measure:** semantic duplication. Two functions that do the same thing with different
identifiers and structure are invisible to token matching.

This gate targets a failure mode specific to agents: an agent that cannot find the existing helper
writes a second one, and every individual edit looks reasonable. Nothing else in the gauntlet detects
that. jscpd was chosen over pylint's `duplicate-code` because it is language-agnostic and will serve
the C# adapter unchanged — at the cost of a Node dependency, which is a real cost and is named here
rather than buried.

---

## Contracts

Three consumers — a human at a terminal, CI, and an agent hook — share one contract.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Every selected gate passed |
| 1 | Gauntlet could not run: missing or invalid config, unknown gate |
| 2 | Gates failed |

The 1/2 split matters more than it looks. Claude Code treats exit 2 as blocking and **exit 1 as a
non-blocking error that is ignored**. So a broken `gauntlet.toml` fails open — the agent is not
wedged by a config typo — while a genuine gate failure blocks. Passing reports go to stdout, failing
reports to stderr, because agent hooks feed stderr back into the model's context.

### JSON report

```json
{
  "passed": false,
  "gates": [
    {
      "gate": "complexity",
      "passed": false,
      "threshold": 6,
      "actual": 9,
      "duration": 0.09,
      "error": null,
      "diagnostics": [
        {
          "file": "src/rating.py",
          "message": "calculate has cyclomatic complexity 9 (max 6). Extract the branching logic into helper functions until it is <= 6.",
          "symbol": "calculate",
          "line": 42,
          "value": 9
        }
      ],
      "diagnostics_truncated": 0
    }
  ]
}
```

Three deliberate properties:

- **`error` is separate from `passed`.** "The tool crashed" and "the gate legitimately failed" call
  for completely different agent behavior, and conflating them is a common harness bug.
- **Diagnostics are prescriptive.** Every message names the remedy, not just the fact. "CC is 9 (max
  6)" is a measurement; "extract the branching logic into helper functions" is an instruction. A
  capable model infers the first from the second; a small one does not.
- **Output is budgeted and honest about it.** Diagnostics are sorted worst-first and capped at
  `max_diagnostics_per_gate`, with `diagnostics_truncated` reporting what was hidden. Weak models
  thrash when handed fifty findings at once; `--fail-fast` narrows it further to one coherent problem
  at a time.

### Configuration

Gauntlet searches upward from the working directory for `gauntlet.toml`, so it runs correctly from
any subdirectory — which matters because agent hooks fire with an unpredictable working directory.

Artifacts are written to `.gauntlet/` (gitignored): `junit.xml`, `coverage.json`, and the jscpd
report. These are the join inputs for CRAP and are left in place deliberately.

---

## Continuous integration

`.github/workflows/gauntlet.yml` runs `gauntlet check --json` and passes or fails on the exit code —
the same contract the agent hooks use. The report is uploaded as an artifact even on failure.

For real enforcement, add a branch protection rule requiring the `gauntlet` check on `main`. A gate
you can merge around is not a gate.

---

## Agent integration

**Not yet implemented — this is the Phase 3 design.**

`gauntlet init --agent claude-code` will generate:

- **`PostToolUse`** (matcher `Edit|Write|MultiEdit`) → the fast gates on changed files only,
  sub-two-second feedback after every edit. Note that PostToolUse **cannot block** — the edit has
  already happened — but its stderr is shown to the model, so it acts as an immediate correction
  signal rather than a gate.
- **`Stop`** → the full gauntlet. Exit 2 prevents the agent from finishing and feeds the failure
  report back into its context, so it keeps working. Bounded by a retry counter: after N consecutive
  failures the hook gives up and asks for a human, because an agent that cannot fix the problem
  should not loop forever.
- **`PreToolUse`** → `gauntlet guard`, which reads the hook JSON on stdin and blocks writes to
  protected paths (`gauntlet.toml`, the artifact directory, the spec registry, the hook config
  itself). A threshold an agent can edit is not a threshold.
- **A `CLAUDE.md` block** — advisory context only, never enforcement. It is worth including anyway:
  capable models demonstrably read ambient signals and raise their own bar in response. It is cheap
  insurance for strong models and harmless for weak ones. The gates remain the only thing relied
  upon.

Hook output is capped at 10,000 characters by Claude Code, which is why the diagnostic budget is a
real constraint rather than a formatting preference.

**Tool-agnostic mode** (`--agent generic`) will emit a pre-commit hook and the CI workflow. Anything
that can run a shell command can be gated; only the tight in-loop feedback is Claude Code specific.

**`gauntlet loop -- <agent command>`** (Phase 3.5) will drive agents that cannot be hooked at all:
run the agent, run the gauntlet, feed the JSON report back as the next prompt, repeat to a cap. This
is deliberately dumb — the moment it grows roles and handoffs it becomes multi-agent orchestration,
which is explicitly out of scope.

---

## What building this taught us

These are findings from the build, kept because they are the most interesting content in the
project.

**A frontier model's self-imposed standards converge near the same ceiling — but only by accident.**
In the initial spike, Claude Code (Opus, maximum effort) was given a premium proration task and no
instructions about quality. It noticed `pytest-cov` and `mutmut` in the dev dependencies, inferred
that test quality mattered, and delivered 73 tests, 100% coverage, and 131 of 133 mutants killed —
with a maximum cyclomatic complexity of exactly 6, the ceiling it was never told about. Independent
verification confirmed every claim.

That is a genuinely impressive result and a bad thing to depend on. The self-policing hinged on the
model noticing a dependency and choosing to honor it. Rules in prompts decay; *rules in ambient
signals* were never rules at all.

**Gauntlet failed its own gates on the first honest run.** Eight functions over the complexity
ceiling, the worst being `check` in `cli.py` at CC 15 — in a tool whose purpose is enforcing a
complexity limit of 6, written with a frontier model's help. The refactor the gate demanded was not
cosmetic: it forced parsing and judging apart from subprocess orchestration in every gate, which is
what made the pure functions unit-testable without mocking. The gate found the design flaw before
either author did.

**Each gate caught something the others could not.** A stray trailing comma turned a string into a
one-element tuple. Ruff flagged it as "did you forget a comma?" — the opposite of the real problem.
Mypy said nothing, because a list of tuples is only wrong once `"\n".join` sees it. The tests gate
caught it. Separately, an integration test against a real git repository exposed that `git status
--porcelain` collapses untracked directories into a single entry, so `--changed` was silently missing
every newly created file — invisible to the unit tests, which had all passed.

**CRAP earned its place within minutes of existing.** The first run after the gate landed flagged
`duplication.run` at 16.58 — complexity 4 at 8% coverage. The complexity gate passed it (4 ≤ 6). The
coverage gate passed the file. Only the intersection failed.

**Mutation testing is cheaper than expected, and equivalent mutants are real.** mutmut 3 ran 133
mutants in 5.6 seconds on the spike project, an order of magnitude faster than the "nightly CI only"
assumption, because it mutates in-process and runs only the tests that touch each mutant. It also hit
a principled ceiling: two surviving mutants that provably cannot change behavior. A mutation gate set
to require 100% is therefore unachievable on real code, which is why Phase 5 pairs a percentage
threshold with a human-approved equivalent-mutant registry — keyed on a hash of the mutation diff,
because mutmut's mutant IDs are positional and shift when the code moves.

---

## Honest limitations

- **Python only.** The adapter split exists in the architecture but has not been exercised by a
  second language. Until the C# adapter ships, "language-agnostic" is a design intention, not a
  demonstrated property.
- **Gates measure proxies.** Every metric here is a proxy for quality, and proxies can be satisfied
  without the quality. That is why the gates overlap: coverage counters empty test suites only when
  paired with mutation testing; complexity limits counter tangled code but not bad names or wrong
  abstractions. Nothing in this tool checks whether the code does the right thing — that is what the
  acceptance pipeline in Phase 4 is for.
- **Agents can game gates.** This is not a bug so much as the interesting part. Each gaming vector
  gets a counter-gate: tests that assert nothing → mutation testing; editing an approved spec →
  hash locking; weakening a threshold → protected paths. The arms race is documented rather than
  hidden, and it is not finished.
- **The duplication gate needs Node.** A Python tool with a JavaScript dependency is a real cost. It
  is justified by the C# adapter reusing it, and the gate degrades to a clear "install jscpd" error
  rather than silently passing.
- **`--changed` compares against the working tree, not a merge base.** It is designed for the
  edit-time agent loop, not for pull-request diffing.
- **Nothing here replaces human judgment about specifications.** Gauntlet moves the human's attention
  from implementation to specifications and thresholds. It does not remove the human.

---

## Roadmap

- **Phase 4 — acceptance pipeline.** Gherkin features as the human-reviewed artifact, hash-locked on
  approval so an agent cannot quietly rewrite the spec to fit the code, with mutation of Example
  table values to prove the acceptance tests are connected to real behavior rather than decorative.
- **Phase 5 — mutation testing.** mutmut integration with per-survivor diffs as diagnostics,
  changed-file scope by default, full runs nightly, and a hash-keyed registry of human-approved
  equivalent mutants.
- **Phase 6 — C# adapter.** coverlet, Roslyn analyzers, Stryker.NET, Reqnroll, driven by a real
  rating-engine application rather than built speculatively.
- **Multi-agent orchestration is explicitly out of scope.** Isolated worktrees, role packs, and
  structured handoffs multiply the scope several times over, and most of their value depends on the
  gates existing first. A finished single-agent harness beats a half-built swarm.

---

## Credits

The methodology is Robert C. Martin's ([@unclebobmartin](https://x.com/unclebobmartin)), including
the CRAP metric ceiling, the cyclomatic complexity limit of 6, the acceptance-pipeline structure, and
the central premise that the implementation code is the agent's business and the metrics are yours.
His reference implementations are worth reading:

- [swarm-forge](https://github.com/unclebob/swarm-forge) — multi-agent orchestration
- [Acceptance-Pipeline-Specification](https://github.com/unclebob/Acceptance-Pipeline-Specification)

Gauntlet is an independent implementation of the ideas, not a port of his tools.

## License

MIT
