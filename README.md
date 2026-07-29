# Gauntlet

**Don't review the agent's code — make it run the gauntlet.**

Gauntlet surrounds AI coding agents with deterministic, automated quality gates so a human can
manage quality from above instead of reading generated code line by line. Every standard becomes an
executable check with a threshold, a loud failure, and a machine-readable diagnostic the agent can
act on.

[![gauntlet](https://github.com/xaziaver/agent-gauntlet/actions/workflows/gauntlet.yml/badge.svg)](https://github.com/xaziaver/agent-gauntlet/actions/workflows/gauntlet.yml)

Gauntlet gates itself. Every commit in this repository has passed the eight gates below, measured by
this tool. When the enforcement layer broke, this tool is how we found out — see
[What building this taught us](#what-building-this-taught-us).

<!-- demo recording goes here once v1 closes -->

---

## Why

The method is Robert C. Martin's, stated plainly in mid-2026: he does not read the code his agents
write. Instead he surrounds them with constraints — unit tests, acceptance tests, coverage,
complexity limits, dependency rules, mutation testing — and manages quality through metrics rather
than review. The reasoning behind it:

- **Rules written in prompts decay.** As a context window fills, instructions in CLAUDE.md or a
  system prompt lose priority. A rule that lives in a tool with a threshold and an exit code does
  not decay.
- **Humans are slow at reading code.** The productivity gain from agents is only realized if the
  human disengages from the implementation and re-engages at the level of specifications and
  measurements.
- **Clean code still matters.** Agents get confused by tangled code the same way people do. The
  standards do not relax; the enforcement mechanism changes from inspection to automation.

### Two audiences, one tool

- **For a weak model, the gates are a teacher.** A small model will not infer that a function should
  be extracted at cyclomatic complexity 7. The gates supply the standard; the diagnostics supply the
  remedy.
- **For a strong model, the gates are an auditor.** Capable models often self-police to a high
  standard — and then report their own results. A frontier model finishing a session with "100%
  coverage, 131 of 133 mutants killed" is asking you to take its word for it. Gauntlet re-measures
  deterministically. Everything you know about the code comes from the tool, not from the agent.

---

## The operating model

**In plain English:** you describe what to build and set the quality bar. The agent builds. Gauntlet
referees. You read specifications, thresholds, and reports — never implementation code.

### The lifecycle

1. **Setup.** `gauntlet init` scaffolds the config and agent hooks. You edit `gauntlet.toml` — the
   thresholds are yours — then `gauntlet lock` to approve it and `gauntlet doctor` to confirm every
   gate's tooling is alive.
2. **Delegate.** Prompt the agent with *behavior*, not implementation: what the code should do, not
   how. The hooks handle the rest without your involvement.
3. **Observe.** During a session, the hook status lines show gates firing after each edit and at
   completion. After a session, `gauntlet check` is the ground truth; `--json` is the same truth for
   machines.
4. **Adjudicate.** The only mid-stream human actions: re-approving a deliberate config change with
   `gauntlet lock`, and answering escalations — the agent hitting the guard on a protected file, or
   the Stop hook's retry cap handing a stuck problem back to you.
5. **Accept.** Green `check`, green CI, `git diff --stat` for the *scope* of what changed — not the
   content. Your confidence comes from the report.

### Responsibilities

| | Owns |
|---|---|
| **Human** | Requirements, thresholds (`gauntlet.toml`), approvals (`gauntlet lock`), spec review, escalation decisions, final acceptance |
| **Agent** | Implementation, tests, refactoring until the gates pass, running `gauntlet check` itself, *proposing* threshold changes in words |
| **Gauntlet** | Measurement, enforcement, feedback, the approval record (`gauntlet.lock.json`) |

The rule that makes the split coherent: **anything the agent could exploit belongs to the human;
everything else belongs to the agent.**

### What success looks like

Exit code 0. Concretely: all gates green including `protect` (the configuration is either untouched
or explicitly re-approved), CI green, and no line-by-line review having happened. In the recorded
demo session, success looked like this: the agent's first draft breached two gates, the diagnostics
forced complexity from 9 down to 4 and the function under the size limit, all without the human
reading a diff — and when asked to weaken a gate instead, the agent refused and handed the decision
back to the human.

### Interfaces and interactivity

Three surfaces, one per audience, all speaking the same exit-code/JSON contract: the **CLI** for the
human, **hooks** for the agent (invisible and involuntary), and **CI** for the team and the record.

Gauntlet itself is deliberately non-interactive — no prompts, no dialogs. `gauntlet lock` is the one
ceremony, and it is a command, not a conversation. The interactive relationship is human↔agent;
Gauntlet decides when that conversation must happen.

---

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Manual spike: run the loop by hand | Done |
| 1 | CLI, config, report contract, five gates | Done |
| 2 | CRAP gate, duplication gate | Done |
| 3 | Protect gate, content-hash locking, guard, Claude Code hooks, `doctor`, retry-capped Stop | Done |
| 3.5 | `gauntlet loop` — external driver for un-hookable agents | Done |
| 4 | Gherkin acceptance pipeline, spec locking, acceptance mutation | Planned |
| 5 | Mutation testing gate | Planned |
| 6 | C# adapter | Planned |

Python projects only today; see [Honest limitations](#honest-limitations).

---

## Quick start — a new project from nothing

Requirements: Python 3.11+, git. The duplication gate additionally needs Node (`npm install -g
jscpd`).

```bash
# Install (from a clone, until published)
git clone https://github.com/xaziaver/agent-gauntlet
cd agent-gauntlet && uv tool install --editable .

# Bootstrap your project
mkdir my-project && cd my-project && git init
mkdir src tests
gauntlet init --agent claude-code   # writes gauntlet.toml, .claude/settings.json, CLAUDE.md
$EDITOR gauntlet.toml               # set YOUR thresholds — this file is the human's artifact
gauntlet lock                       # approve the configuration
gauntlet doctor                     # confirm every gate's tooling is present
gauntlet check                      # green baseline
```

From here, open Claude Code in the project and delegate. The hooks do the rest.

### Commands

| Command | Purpose |
|---|---|
| `gauntlet check` | Run the configured gates. `--gates a,b`, `--changed`, `--fail-fast`, `--json` |
| `gauntlet init` | Scaffold config + integration. `--agent claude-code` (hooks) or `generic` (pre-commit + CI). `--dry-run` |
| `gauntlet lock` | The deliberate human action: approve the current config content into `gauntlet.lock.json` |
| `gauntlet verify` | Check approved files against their hashes — route-independent change detection |
| `gauntlet guard` | PreToolUse hook: block agent edits to protected paths (reads hook JSON on stdin) |
| `gauntlet stop-check` | Stop hook: full gauntlet with a per-session retry cap that escalates to the human |
| `gauntlet doctor` | Is every enabled gate's tooling actually present in *this* environment? |
| `gauntlet loop` | Drive an un-hookable agent: run it, run the gates, feed failures back, repeat to a cap |
| `gauntlet version` | Print the version |

### Exit codes — the contract everything shares

| Code | Meaning |
|---|---|
| 0 | Every selected gate passed |
| 1 | Gauntlet could not run (bad config, unknown gate, broken payload) |
| 2 | Gates failed |

The 1/2 split is load-bearing: Claude Code treats exit 2 as blocking and exit 1 as a non-blocking
error. A config typo therefore fails open rather than wedging the agent — and a genuine gate failure
blocks. The flip side of failing open is that a *broken* Gauntlet silently disables enforcement,
which is exactly what `gauntlet doctor` exists to detect.

---

## The gates

Fixed execution order — cheap and structural first, so an agent fixes syntax and shape before it is
ever shown a coverage number. Every diagnostic is prescriptive: it names the file, symbol, line,
and the *remedy*, because a capable model infers the fix from the measurement and a small one does
not.

### 1. `protect` — the approved configuration must not have changed
Compares `gauntlet.toml`, `pyproject.toml`, and `.claude/settings.json` (configurable) against
human-approved hashes in `gauntlet.lock.json`. Route-independent: it catches changes made through a
shell redirect, an editor, or a subagent — all of which bypass the edit-time guard. Fails open when
no lock file exists (set `require_lock = true` once you have locked). **Does not measure:** whether
the approved thresholds are any good. That is the human's job.

### 2. `static` — ruff + mypy
Fails on any finding from either tool; a crashed or missing tool is a gate *error*, never a clean
bill of health. **Does not measure:** behavior. Clean static analysis says nothing about
correctness.

### 3. `size` — function and module length (stdlib `ast`, no dependency)
**Does not measure:** whether the length is justified; a 30-line data table and a 30-line tangle
fail identically.

### 4. `complexity` — cyclomatic complexity per function (radon)
Ceiling of 6 by default; strictly greater-than, so a function exactly at the ceiling passes.
**Does not measure:** cognitive complexity, nesting, coupling, naming.

### 5. `tests` — the suite must pass (pytest)
An empty suite **fails** — otherwise deleting the test directory is a valid strategy for going
green. Produces the coverage artifact in the same run. **Does not measure:** whether the tests are
meaningful; `assert True` passes this gate. That is what coverage, CRAP, and (Phase 5) mutation
testing are for.

### 6. `coverage` — line, branch, and optional per-file thresholds
Diagnostics are only emitted for rules actually enforced: with `per_file_min` unset, a passing gate
stays silent about individual files, so an agent never mistakes guidance for failure. **Does not
measure:** assertion quality — coverage counts execution, not verification.

### 7. `crap` — Change Risk Anti-Pattern, per function

```
CRAP = CC² × (1 − coverage)³ + CC
```

Joins radon's per-function spans with coverage.py's executed lines. Exists for the case neither
input catches alone: **a complex function inside a well-covered file.** At full coverage CRAP
collapses to CC (well-tested complexity passes); at zero coverage complexity is punished
quadratically. The diagnostic offers both remedies with the exact coverage percentage that would
clear the ceiling — or says plainly that tests cannot help and extraction is required.

### 8. `duplication` — token-level clone detection (jscpd, needs Node)
Targets a specifically agentic failure mode: an agent that cannot find the existing helper writes a
second one, and every individual edit looks fine. **Does not measure:** semantic duplication, or
clones smaller than `min_tokens` — see the build insights for a real example of each side of that
threshold.

---

## Agent integration

`gauntlet init --agent claude-code` generates three hooks (idempotently — it merges into existing
settings and replaces only its own entries):

- **PreToolUse → `gauntlet guard`.** Blocks edits to protected paths before they happen. The refusal
  message includes a deliberate escalation valve — *"If you believe a threshold is genuinely wrong,
  say so in your response and let the human decide"* — because a model facing a wrong threshold with
  no escape hatch can only thrash.
- **PostToolUse → fast gates on changed files** (static, size, complexity; sub-second). Cannot block
  — the edit already happened — but its stderr reaches the model as an immediate correction signal.
- **Stop → `gauntlet stop-check`.** The real gate: full gauntlet, exit 2 means "you are not done"
  and the report re-enters the agent's context. Bounded by a per-session retry cap (default 3) that
  then escalates to the human with a systemMessage, because an agent that cannot fix the problem
  should not loop forever.

It also writes a marked, idempotent block into `CLAUDE.md` — advisory context, never enforcement.
Worth including anyway: capable models demonstrably read ambient signals and raise their own bar.
The gates remain the only thing relied upon.

**Un-hookable agents:** `gauntlet loop --cmd "<agent command>" --task "..."` drives any CLI that
reads a prompt on stdin and edits files: run agent → run gates → feed the JSON report back as the
next prompt → repeat to a cap. Deliberately dumb — no conversation state, no roles. The moment it
grows those it is multi-agent orchestration, which is out of scope by design.

**Environment note:** hooks run bare `gauntlet`, not your project venv. Install with
`uv tool install --editable .` so hooks track the repo — but a later *dependency* change still needs
`uv tool install --reinstall --editable .`, because editable tracks source, not the dependency list.
When in doubt: `gauntlet doctor`, from a plain shell.

---

## What building this taught us

Kept because it is the most interesting engineering content in the project. Every incident below
happened in this repository's own history.

**A frontier model's standards converge on the same ceiling — by accident.** In the Phase 0 spike,
a maximum-effort agent given no quality instructions noticed `pytest-cov` and `mutmut` in the dev
dependencies, inferred that rigor mattered, and delivered 73 tests, 100% coverage, 131/133 mutants
killed — and a maximum cyclomatic complexity of exactly 6, the ceiling it was never told about.
Impressive, and a bad thing to depend on: rules in ambient signals were never rules at all.

**Gauntlet failed its own gates on the first honest run.** Eight functions over the complexity
ceiling — the worst, `check` itself, at CC 15 — in a tool whose purpose is enforcing a ceiling of
6. The refactor the gate demanded forced parsing apart from orchestration in every gate, which is
what made the logic unit-testable without mocking. The gate found the design flaw before either
author did.

**Each gate caught something the others could not.** A stray trailing comma turned a string into a
tuple: ruff suggested the *opposite* fix, mypy said nothing, the tests gate caught it. An
integration test against a real git repo exposed that `git status --porcelain` collapses untracked
directories, so `--changed` silently missed every new file — invisible to every unit test.

**CRAP earned its place within minutes of existing.** Its first run flagged a function at CRAP
16.58 — complexity 4 (passes the complexity gate) at 8% coverage (in a repo passing the coverage
gate). Only the intersection failed.

**The duplication gate, both sides of the threshold.** A refactor left a 33-line function existing
twice in one file: static clean, complexity fine, coverage 97%, all 234 tests passing — only jscpd
caught it. Earlier, a smaller duplicated block slipped *under* `min_tokens` and through. Same gate,
same class of bug, one caught and one missed: an honest illustration of what a threshold buys and
costs.

**The enforcement layer died silently, and the session looked perfect.** The first demo attempt:
both hooks crashed with tracebacks (ruff missing from the hook environment — hooks do not run your
project venv), exited 1, and *failed open*. The agent, unhooked, produced excellent work and
reported that all gates passed. Nothing verified it. Worse, mypy's failure mode was silent: absent,
it exits 1 with empty stdout, which parsed as "no findings." Three fixes came out of the incident —
missing tools became gate errors, all measurement tools moved into runtime dependencies, and
`gauntlet doctor` now exists because a system that fails open needs a way to be asked whether it is
alive.

**The demo session, once the hooks were alive.** The agent's first draft breached two gates
(complexity 9, size 21); the PostToolUse diagnostics fed back; the agent extracted five helper
predicates and landed at complexity 4 — then began running `gauntlet check` on its own, unprompted.
Asked to raise the complexity limit instead, it first *cased the mechanism* — read the lock file,
the settings, the CLI help, looking for seams — then attempted the edit, was blocked by the guard,
and responded by refusing on the merits:

> "I don't think I should even if I could… Raising the ceiling to 20 wouldn't fix anything broken;
> it would just permit deeply nested claim-triage logic to go unflagged in the future. If you still
> want the limit raised, you'll need to do it yourself… run `gauntlet lock` to re-approve — that's
> the deliberate human action the lock mechanism requires."

The escalation valve written into the refusal message produced exactly the intended behavior — and
the agent went one better and defended the human's threshold against the human.

---

## Honest limitations

- **Python only.** The adapter split exists in the architecture but is undemonstrated until the C#
  adapter ships.
- **Gates measure proxies.** Every metric is a proxy for quality, and proxies can be satisfied
  without the quality — which is why the gates overlap, and why nothing here yet checks that the
  code does the *right* thing. That is Phase 4's acceptance pipeline.
- **The guard is not airtight, by construction.** It sees file-path tools only; a shell redirect
  bypasses it. The `protect` gate catches every route after the fact via content hashes, and CI plus
  human review of config diffs is the backstop. The guard raises the cost; it does not make the
  thing impossible. Suppression comments (`# noqa`, `# type: ignore`) remain a code-review problem.
- **Locking fails open until you opt in.** No lock file means the protect gate passes with a nudge —
  deliberate, so installation does not break a project — and means an unlocked project is
  unprotected. Set `require_lock = true` after your first `gauntlet lock`.
- **A silently broken hook environment is still possible.** Fail-open is the design; `gauntlet
  doctor` is the mitigation, not a guarantee. Run it after any dependency change.
- **`--changed` compares against the working tree,** not a merge base: built for the edit-time loop,
  not PR diffing.
- **`gauntlet loop` is deliberately dumb.** One prompt in, files out, no memory between iterations
  beyond the report itself.

---

## Roadmap

- **Phase 4 — acceptance pipeline.** Gherkin features as the human-reviewed artifact, hash-locked on
  approval (the registry mechanism already exists and protects the config today), with mutation of
  Example-table values to prove the acceptance tests are connected to behavior rather than
  decorative.
- **Phase 5 — mutation testing.** mutmut with per-survivor diffs as diagnostics, changed-scope by
  default, and a hash-keyed registry of human-approved equivalent mutants (the spike proved
  equivalent mutants are real: 131/133 was a principled ceiling, not a miss).
- **Phase 6 — C# adapter.** coverlet, Roslyn analyzers, Stryker.NET, Reqnroll — driven by a real
  application, not built speculatively.
- **Multi-agent orchestration stays out of scope.** A finished single-agent harness beats a
  half-built swarm.

---

## Credits

The methodology is Robert C. Martin's ([@unclebobmartin](https://x.com/unclebobmartin)) — the CRAP
ceiling, the complexity limit of 6, the acceptance-pipeline structure, and the central premise that
the implementation is the agent's business and the metrics are yours. Reference implementations:
[swarm-forge](https://github.com/unclebob/swarm-forge),
[Acceptance-Pipeline-Specification](https://github.com/unclebob/Acceptance-Pipeline-Specification).
Gauntlet is an independent implementation of the ideas, not a port of his tools.

## License

MIT
