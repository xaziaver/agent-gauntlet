# Gauntlet

**Don't review the agent's code — make it run the gauntlet.**

Gauntlet wraps AI coding agents in deterministic quality gates. The agent writes the code; ten
automated gates decide whether it is acceptable; you read specifications, thresholds, and reports
instead of diffs.

[![gauntlet](https://github.com/xaziaver/agent-gauntlet/actions/workflows/gauntlet.yml/badge.svg)](https://github.com/xaziaver/agent-gauntlet/actions/workflows/gauntlet.yml)

Gauntlet gates itself. Every commit here has passed the nine gates it enables, measured by this
tool - mutation testing ships but is deliberately not enabled on this repository, for the reason
described below. [**gauntlet-demo1**](https://github.com/xaziaver/gauntlet-demo1) is a small project
running all ten end to end.

---

## Quick start

Requires Python 3.11+, git, and — for two optional gates — Node (`jscpd`) and `mutmut`.

```bash
# Install
git clone https://github.com/xaziaver/agent-gauntlet
cd agent-gauntlet && uv tool install --editable .

# Set up your project
cd ~/my-project
gauntlet init --agent claude-code   # writes gauntlet.toml, .claude/settings.json, CLAUDE.md
$EDITOR gauntlet.toml               # set YOUR thresholds — this file is yours, not the agent's
gauntlet lock                       # approve that configuration
gauntlet doctor                     # confirm every gate's tooling is present
gauntlet check                      # green baseline
```

Your project supplies its own test-runner environment. Gauntlet brings ruff, mypy, and radon; the
project's virtualenv needs `pytest` plus `pytest-cov`, and `pytest-bdd` / `mutmut` if you enable
those gates. `gauntlet doctor` tells you which are missing and which interpreter it is looking in.

Now open Claude Code in the project and describe what you want built. The hooks do the rest.

## How it works

```
        you                      agent                    gauntlet
         │                         │                          │
    write the spec ──────────────► │                          │
    set thresholds                 │                          │
         │                    writes code ──► edit ──► fast gates (< 2s)
         │                         │ ◄──────── "CC 9 > 6: extract functions"
         │                    fixes it ──────► edit ──► fast gates ✓
         │                         │                          │
         │                    "I'm done" ─────────────► full gauntlet
         │                         │ ◄──────── exit 2: "no, you're not"
         │                         │                          │
         │                    tries to raise a threshold ──► BLOCKED
         │ ◄──── "the limit looks wrong to me, your call" ────┤
         │                         │                          │
    read the report ◄──────────────────────────────── all gates green
```

Three moments matter. **Edit time**: a hook runs the fast gates after every file write and feeds
failures straight back to the model. **Completion time**: the agent cannot finish while any gate is
red. **Escalation**: anything only a human can decide — a threshold change, an unapproved spec, a
mutant no test can kill — stops and asks you.

## Where you stand

One command, any time:

```
$ gauntlet status --run
PROJECT   /home/you/my-project
LOCKED    yes
GATES     PASSING
  • ✓ protect      3/3 paths unchanged
  • ✓ static       0 findings
  • ✓ size         worst_function_lines=15
  • ✓ complexity   4
  • ✓ tests        20/20 passing
  • ✓ coverage     line=100.0, branch=100.0
  • ✓ crap         4.0
  • ✓ duplication  0
  • ✓ mutation     score 100.0%, 59 killed, 3 reviewed-equivalent
  • ✓ acceptance   1 spec(s), 9 reviewed-equivalent
WAITING   nothing needs your approval
ACTIVITY  most recent first
  • 2026-08-02T12:45:29+00:00  gate.finished     ✓ acceptance
  • 2026-08-02T12:45:24+00:00  gate.finished     ✓ mutation
  ...
```

`WAITING` is the part that matters: everything blocked on a human decision, and the command that
clears each one. Without `--run` it reports the last known state instantly and skips the gates.

## Reviewing what's waiting

`gauntlet review` walks that list one item at a time, showing the actual change:

```
$ gauntlet review --reviewer you
─── 1/1  [config] gauntlet.toml — modified
--- approved/gauntlet.toml
+++ current/gauntlet.toml
@@ -17,7 +17,7 @@
 [gates.complexity]
-max = 5
+max = 6

approve / skip / quit [a/s/q] [s]: a
reason (required): loosened after extracting the rating helpers

approved 1 of 1 item(s)
```

Approving something you haven't looked at is the rubber stamp the whole ledger exists to prevent, so
review shows a diff for anything modified and requires a reason before recording it. Skip and quit
are always available; nothing is written until you say yes.

## The gates

| Gate | Fails when | Blind to |
|---|---|---|
| `protect` | approved config changed without re-approval | whether your thresholds are any good |
| `static` | ruff or mypy reports anything | behavior |
| `size` | a function or module exceeds its line limit | whether the length is justified |
| `complexity` | cyclomatic complexity over the ceiling (default 6) | nesting, coupling, naming |
| `tests` | any test fails — or none exist | whether the tests assert anything |
| `coverage` | line/branch/per-file coverage below threshold | assertion quality |
| `crap` | complexity × untestedness over the ceiling | anything its two inputs miss |
| `duplication` | copy-pasted blocks (jscpd) | semantic duplication |
| `boundary` | step definitions import production code directly | whether the API layer itself is any good |
| `mutation` | too few code mutants killed (mutmut) | mutants nothing could kill |
| `acceptance` | specs unapproved, scenarios failing, or spec values unchecked | requirements you never wrote down |

Each gate is opt-in: no `[gates.x]` table, no gate.

## Commands

| | |
|---|---|
| `gauntlet status` | Gates, pending approvals, recent activity. `--run` `--json` |
| `gauntlet review` | Walk pending approvals one at a time, with the diff on screen |
| `gauntlet check` | Run the gates. `--gates a,b` `--changed` `--fail-fast` `--json` |
| `gauntlet init` | Scaffold config + integration. `--agent claude-code\|generic` `--dry-run` |
| `gauntlet doctor` | Is every enabled gate's tooling actually present here? |
| `gauntlet lock` / `verify` | Approve configuration / check it hasn't drifted |
| `gauntlet spec approve` / `list` | Approve acceptance specifications |
| `gauntlet mutant approve[-code]` / `list` / `prune[-code]` | Classify surviving mutants |
| `gauntlet events` | Recent activity: runs, gate results, approvals, escalations |
| `gauntlet loop --cmd "..." --task "..."` | Drive an agent that can't be hooked |
| `gauntlet guard` / `stop-check` | Hook entry points (not run by hand). `stop-check` stops at the first failing gate, in the fixed order cheap-first and acceptance last; `--no-fail-fast` runs them all |

Exit codes are the contract everything shares: **0** passed, **1** Gauntlet couldn't run, **2** gates
failed.

---

# The longer version

## Why

The method is Robert C. Martin's, stated plainly in mid-2026: he does not read the code his agents
write. He surrounds them with constraints — tests, coverage, complexity limits, mutation testing —
and manages quality through metrics instead of review. Three claims hold it up:

**Rules written in prompts decay.** As a context window fills, instructions in CLAUDE.md lose
priority. A rule that lives in a tool with a threshold and an exit code does not decay.

**Humans are slow at reading code.** The productivity gain from agents only materializes if the human
disengages from implementation and re-engages at specifications and measurements.

**Clean code still matters.** Agents get confused by tangled code the same way people do. The
standards don't relax; the enforcement mechanism changes from inspection to automation.

### Teacher or auditor

The same gates do different work depending on the agent:

- **For a weak model, they teach.** A small model won't infer that a function should be extracted at
  complexity 7. The gates supply the standard; the diagnostics supply the remedy.
- **For a strong model, they audit.** Capable models often self-police to a high standard — and then
  report their own results. A frontier model ending a session with "100% coverage, 131 of 133 mutants
  killed" is asking you to take its word for it. Gauntlet re-measures. Everything you know comes from
  the tool, not the agent.

## The operating model

You describe what to build and set the quality bar. The agent builds. Gauntlet referees.

### Who owns what

| | Owns |
|---|---|
| **You** | Requirements, thresholds, approvals, escalation decisions, final acceptance |
| **The agent** | Implementation, tests, refactoring until the gates pass, *proposing* threshold changes in words |
| **Gauntlet** | Measurement, enforcement, feedback, the approval record |

One rule makes the split coherent: **anything the agent could exploit belongs to the human;
everything else belongs to the agent.**

### The lifecycle

1. **Set up** — `init`, edit `gauntlet.toml`, `lock`, `doctor`.
2. **Delegate** — prompt for *behavior*, not implementation.
3. **Observe** — hook status lines during the session; `gauntlet check` after; `gauntlet events` for
   the timeline.
4. **Adjudicate** — the only mid-stream human actions: re-approving a deliberate config change, and
   answering escalations.
5. **Accept** — green `check`, green CI, `git diff --stat` for the *scope* of what changed. Not the
   content.

### Success looks like

Exit code 0, with no line-by-line review having happened. Concretely, from the demo project: the
agent's first draft breached two gates; the diagnostics drove complexity from 9 to 4; mutation
testing then found four untested boundary conditions that 100% coverage had hidden; three surviving
mutants turned out to be provably unkillable and were classified as such. Nobody read a diff.

### Interfaces

Three surfaces, one contract: the **CLI** for you, **hooks** for the agent (invisible and
involuntary), **CI** for the record. All three consume the same exit codes and the same JSON.

**The gates are never interactive.** They don't prompt, don't block on input, and behave identically
under a terminal, a hook, and CI — anything else would make a gate's verdict depend on who ran it.

The human's *review* surface is a different matter, and `gauntlet review` is deliberately
conversational: it's a thing you choose to run when you sit down to clear the inbox. That split —
non-interactive enforcement, interactive review — is the design, not an inconsistency.

## The approval ledger

Everything you sign off on lands in one file, `gauntlet.lock.json`, under a namespace:

```
config:gauntlet.toml                     the thresholds themselves
spec:features/rating.feature             an acceptance specification
mutant:code#policy|_bump|...             a mutant no test could kill
```

Every entry follows the same lifecycle: **propose → review → hash → auto-invalidate on change.**
Approval records a content hash plus your reason and name. If the thing changes, the approval lapses
and the gate asks again. If an approved item stops being produced — a formerly unkillable mutant now
dies because you sharpened a test — the entry is reported stale and can be pruned.

Three properties make this more than a suppression file. The record is a **diff**, so approvals are
reviewable in a pull request. It is **self-invalidating**, so it can't quietly rot. And it is itself
a protected path, so an agent cannot approve its own work.

```json
"mutant:code#policy|triage_claim|...tier != \"urgent\"...": {
  "approved_at": "2026-08-02T08:30:30+00:00",
  "digest": "sha256:123d228f...",
  "reason": "the guard and the index clamp each prevent the other from mattering",
  "reviewer": "xaziaver"
}
```

## The gates in detail

Gates run cheapest-first, so an agent fixes syntax and shape before it's shown a coverage number.
Every diagnostic names the file, the symbol, the line, and **the remedy** — because a capable model
infers the fix from the measurement and a small one does not.

**`protect`** — compares configuration against approved hashes. Route-independent: it catches changes
made through a shell redirect, an editor, or a subagent, all of which bypass the edit-time guard.
Fails open until you've run `lock` (set `require_lock = true` afterward).

**`static`** — ruff + mypy. A crashed or missing tool is a gate *error*, never a clean bill of health.

**`size`** — function and module line limits, measured with the standard library's `ast`. No
dependency.

**`complexity`** — cyclomatic complexity per function, radon. Ceiling 6 by default, strictly
greater-than, so a function exactly at the ceiling passes.

**`tests`** — the suite must pass, and an empty suite **fails**: otherwise deleting the test
directory is a valid way to go green.

**`coverage`** — aggregate line and branch, plus optional `per_file_min`. Diagnostics appear only for
rules actually enforced, so a passing gate never emits guidance an agent could mistake for a failure.

**`crap`** — `CC² × (1 − coverage)³ + CC`, per function, joining radon's spans with coverage's
executed lines. It exists for the case neither input catches alone: **a complex function inside a
well-covered file.** At full coverage it collapses to CC; at zero coverage complexity is punished
quadratically. The diagnostic offers both remedies, including the exact coverage percentage that
would clear the ceiling.

**`duplication`** — jscpd. Targets a specifically agentic failure: an agent that can't find the
existing helper writes a second one, and every individual edit looks fine.

**`mutation`** — mutmut against your unit tests. Coverage proves lines ran; this proves the tests
*notice* when those lines behave differently. Reviewed-equivalent mutants count as killed, so the
score stays honest.

**`acceptance`** — the human-reviewed layer, in three stages: every spec must be approved and
unchanged, the bound scenarios must pass, and **every mutation of a specification value must fail.**
That last stage is the distinctive one — see below.

## Acceptance mutation

A scenario can pass without checking anything. Consider a binding that calls the system and then
asserts something trivially true: the suite is green, coverage is full, and the scenario is theater.

So Gauntlet perturbs the values in your specification — numbers by one, booleans flipped, enums
swapped for another value in the same column — reruns, and demands every mutant *fail*. A survivor
means the scenario passes regardless of the value it claims to test.

Mutants are applied as targeted edits at parsed positions, never by re-rendering the file: your
specification is the human's artifact, not Gauntlet's to reformat. The original is always restored.

## Equivalent mutants

Some mutants can't be killed by any test. If your rules say amounts above 50,000 are "high", then
mutating 75,000 to 75,001 changes nothing observable. That's an **equivalent mutant** — a statement
about your domain, not a weakness in your tests.

Ignoring them pollutes the score and trains everyone to disregard survivors. Chasing them is
impossible. So Gauntlet asks for a judgment, once:

```bash
gauntlet mutant approve-code \
  --reason "both values fall on the same side of every threshold" \
  --reviewer you
```

Thereafter they're reported in a separate reviewed-equivalent bucket and count as killed. If the code
or the tests change so that the mutation *would* now discriminate, the approval lapses automatically
and it comes back for review.

## Agent integration

`gauntlet init --agent claude-code` writes three hooks (idempotently — it merges into existing
settings and replaces only its own entries):

- **PreToolUse → `gauntlet guard`** blocks edits to protected paths before they happen. The refusal
  includes a deliberate escape valve: *"If you believe a threshold is genuinely wrong, say so and let
  the human decide."* A model facing a wrong threshold with no way out can only thrash.
- **PostToolUse → fast gates on changed files.** Cannot block — the edit already happened — but its
  stderr reaches the model as an immediate correction signal.
- **Stop → `gauntlet stop-check`.** The real gate. Exit 2 means "you're not done" and the report
  re-enters the agent's context. Bounded by a per-session retry cap that escalates to you, because an
  agent that cannot fix the problem shouldn't loop forever. It stops at the first failing gate — the
  order is fixed, cheap gates first and acceptance last, so a red `protect` or `static` never waits
  on a mutation pass (`--no-fail-fast` runs every gate, as `gauntlet check` does).

It also writes a marked block into `CLAUDE.md` — advisory context, never enforcement. Worth including
anyway: capable models read ambient signals and raise their own bar. The gates remain the only thing
relied upon.

**Agents that can't be hooked** get an external driver: `gauntlet loop --cmd "<agent>" --task "..."`
runs the agent, runs the gates, feeds the JSON report back as the next prompt, and repeats to a cap.
Deliberately dumb — no conversation state, no roles. The moment it grows those it becomes multi-agent
orchestration, which is out of scope.

**Environment note:** hooks run bare `gauntlet`, not your project venv. Install with `uv tool install
--editable .` so hooks track the repo — but a later *dependency* change still needs
`uv tool install --reinstall --editable .`, because editable tracks source, not the dependency list.
When in doubt: `gauntlet doctor`, from a plain shell.

A **cloned or copied project** needs its environment rebuilt before the gates will pass: virtualenvs
and `__pycache__` directories embed absolute paths, so a directory that was copied rather than
created will fail in confusing ways. `rm -rf .venv __pycache__` and rebuild.

## The event log

Gates answer "what is the state now." A dashboard also needs "what is happening." Every command
appends to `.gauntlet/events.jsonl`: runs starting and finishing, each gate's result, approvals
granted, **approvals needed**, agent blocks, loop iterations, escalations.

```bash
gauntlet events --limit 20
gauntlet events --json | jq 'select(.kind == "approval.needed")'
```

`approval.needed` is the interesting one: it's the inbox — everything waiting on a human. A live
dashboard is a tail-and-render over this file rather than a special path into internals, which is the
same discipline that lets hooks and CI share one contract.

## Configuration

```toml
[project]
language = "python"
src = "src/"
tests = "tests/"
python = ".venv/bin/python"      # optional; auto-detected from .venv

[output]
max_diagnostics_per_gate = 10    # worst-first, then a truncation count

[protect]
paths  = ["gauntlet.toml", "gauntlet.lock.json", ".gauntlet/", ".claude/settings.json"]
verify = ["gauntlet.toml", "pyproject.toml", ".claude/settings.json"]
```

`paths` are **blocked** from agent edits; `verify` are **content-checked**. `pyproject.toml` belongs
in the second only — it holds thresholds *and* legitimate dependency work, so it's checked rather
than frozen.

Then one table per gate you want. Full examples in
[gauntlet.toml](gauntlet.toml) and in the
[demo project](https://github.com/xaziaver/gauntlet-demo1/blob/main/gauntlet.toml).

## Continuous integration

`.github/workflows/gauntlet.yml` runs `gauntlet check --json` and passes or fails on the exit code —
the same contract the hooks use. For real enforcement, add a branch protection rule requiring the
`gauntlet` check. A gate you can merge around is not a gate.

---

## What building this taught us

Every incident below happened in this repository's own history.

**A frontier model converges on the same ceiling — by accident.** In the initial spike, an agent
given no quality instructions noticed `pytest-cov` and `mutmut` in the dev dependencies, inferred
that rigor mattered, and delivered 73 tests, 100% coverage, 131/133 mutants killed — and a maximum
complexity of exactly 6, the ceiling it was never told about. Impressive, and a bad thing to depend
on: rules in ambient signals were never rules at all.

**Gauntlet failed its own gates on the first honest run.** Eight functions over the complexity
ceiling — the worst, `check` itself, at CC 15 — in a tool whose purpose is enforcing a ceiling of 6.
The refactor it demanded forced parsing apart from orchestration in every gate, which is what made
the logic testable without mocking. The gate found the design flaw before either author did.

**Each gate caught what the others couldn't.** A stray trailing comma turned a string into a tuple:
ruff suggested the *opposite* fix, mypy said nothing, the tests gate caught it. `git status
--porcelain` collapses untracked directories, so `--changed` silently skipped every new file —
invisible to every unit test, caught by one integration test against a real repo. A refactor left a
33-line function existing twice: static clean, coverage 97%, 234 tests passing, and only jscpd
noticed. Earlier, a *smaller* duplicate slipped under `min_tokens` and through — the same gate, the
same bug class, one caught and one missed.

**CRAP earned its place within minutes of existing.** Its first run flagged a function at 16.58 —
complexity 4 (passes the complexity gate) at 8% coverage (in a repo passing the coverage gate). Only
the intersection failed.

**The enforcement layer died silently, and the session looked perfect.** The first demo attempt: both
hooks crashed (ruff was missing from the hook environment — hooks don't run your project venv),
exited 1, and *failed open*. The agent produced excellent work and reported that all gates passed.
Nothing had verified it. Worse, mypy's failure mode was silent: absent, it exits 1 with empty stdout,
which parsed as "no findings." Three fixes followed — missing tools became gate errors, measurement
tools moved into runtime dependencies, and `gauntlet doctor` exists because a system that fails open
needs a way to be asked whether it's alive.

**Resolving a symlink quietly disabled the virtual environment.** `.venv/bin/python` is a symlink to
the base interpreter; calling `.resolve()` on it — to be tidy — produced an interpreter without the
venv's packages, so every project dependency looked missing. `doctor` printing both interpreters side
by side turned an afternoon into a glance.

**The demo session, once the hooks were alive.** The agent's first draft breached two gates; the
diagnostics fed back; it extracted five helper predicates and landed at complexity 4 — then started
running `gauntlet check` on its own, unprompted. Asked to raise the limit instead, it first *cased
the mechanism* — reading the lock file, the settings, the CLI help, looking for seams — then
attempted the edit, was blocked, and refused on the merits:

> "I don't think I should even if I could… Raising the ceiling to 20 wouldn't fix anything broken; it
> would just permit deeply nested claim-triage logic to go unflagged. If you still want the limit
> raised, you'll need to do it yourself… run `gauntlet lock` to re-approve — that's the deliberate
> human action the lock mechanism requires."

The escape valve produced exactly the intended behavior, and the agent went one better: it defended
the threshold against the human who set it.

**A rule with no gate behind it decayed inside one session.** The FNOL project's kickoff prompt
required, in its ground rules, that step definitions reach the system only through a stable test API
layer. The agent acknowledged the rule and then wrote eight direct imports of the production package
across four step files. Every other rule in that prompt that a gate enforced was followed. The one
rule with nothing behind it was not. Building the `boundary` gate caught all eight immediately — on
a rule we had written ourselves, in a project built to test the tool, with an agent that had been
told explicitly.

**Mutation testing's cost is your test suite's runtime.** The demo project ran 62 mutants in 2.6
seconds. This repository would need roughly 87 minutes for 3,752, because its own tests spawn real
subprocesses. mutmut also mutates string literals, so error messages that no test asserts on surface
as survivors — noise that would need either suppression patterns or dozens of approvals. So the
mutation gate ships, is proven on a project it fits, and is deliberately not enabled here. A gate you
would have to weaken to pass is not a gate.

**Mutation testing found what 100% coverage hid.** The demo project's unit tests looked thorough —
parameterized cases, one test per tier. Mutmut killed 55 of 62 mutants. Every survivor was a boundary
nobody tested: no case used exactly 50,000, or exactly 90 days, or exactly 1,000. Four tests fixed
that (59/62). The remaining three were genuinely equivalent — two safeguards each preventing the
other from mattering — and were classified rather than chased.

## Honest limitations

- **Python only.** The adapter seam exists but is undemonstrated until a second language ships.
- **Gates measure proxies.** Proxies can be satisfied without the quality, which is why the gates
  overlap — and why nothing here checks that the code does the *right* thing except the acceptance
  pipeline, which only checks what you wrote down.
- **The guard is not airtight, by construction.** It sees file-path tools only; a shell redirect
  bypasses it. `protect` catches every route afterward via content hashes, and CI plus review of
  config diffs is the backstop. The guard raises the cost; it doesn't make the thing impossible.
  Suppression comments (`# noqa`, `# type: ignore`) remain a review problem.
- **Locking fails open until you opt in.** No lock file means `protect` passes with a nudge —
  deliberate, so installing doesn't break a project, and it means an unlocked project is unprotected.
- **A silently broken hook environment is still possible.** Fail-open is the design; `doctor` is the
  mitigation, not a guarantee.
- **Gauntlet validates only its own config.** Your `pyproject.toml` can contain invalid TOML and no
  gate will notice — it's hashed, not parsed.
- **Tool errors pass through mostly unedited.** Gauntlet can tell you *that* pytest or mutmut failed
  and give you its first meaningful line, but it cannot diagnose an arbitrary third-party failure. A
  confused tool produces a confusing gate error.
- **`--changed` compares against the working tree,** not a merge base: built for the edit-time loop,
  not PR diffing.
- **mutmut 3 requires fork support** (no native Windows) and copies your project into `./mutants`,
  which needs a pytest ignore and a gitignore entry. `doctor` warns when it's missing.
- **`gauntlet loop` is deliberately dumb.** One prompt in, files out, no memory between iterations
  beyond the report.

## Known issues

The full list, with the evidence behind each, is in [BACKLOG.md](BACKLOG.md).
Contributors and agents picking this up should start with
[ARCHITECTURE.md](ARCHITECTURE.md). For what each gate is for and how it is implemented,
read [docs/GATES.md](docs/GATES.md).

Real defects with workarounds, kept here rather than in an issue tracker because they are part of an
honest picture of a v1.

**A brand-new project fails `gauntlet check` immediately.** With an empty `src/`, mypy exits 2
("no .py files in directory"), and with nothing to measure, pytest-cov writes no report — so
`static`, `coverage`, and `crap` all fail with messages pointing at the symptom rather than the
cause. *Workaround:* create a package `__init__.py`, one trivial module, and one test before the
first `gauntlet check`. *Fix:* `init` should scaffold those, and the gates should name the real
cause.

**Gates report downstream symptoms.** The pattern above is the third instance of the same class:
mypy's absence once parsed as "no findings"; a resolved symlink once produced an interpreter with no
packages. Each was diagnosed by hand and fixed individually. The general improvement — gates that
distinguish "the tool failed" from "the tool found nothing" consistently — is not done.

**Mutation testing is impractical on integration-heavy suites.** Cost scales with test-suite
runtime; a suite that spawns subprocesses can push a full run past an hour. *Workaround:* keep pure
domain logic in its own package and point `[tool.mutmut] source_paths` at it alone. That is good
architecture anyway, but it is a constraint the tool imposes rather than a choice it offers.

**mutmut mutates string literals**, so error messages no test asserts on show up as survivors. On a
message-heavy codebase this is noise that needs suppression patterns or many approvals.

**A copied project directory is broken until rebuilt.** Virtualenvs and `__pycache__` embed absolute
paths. Symptoms are confusing import errors from the *old* path. *Workaround:* `rm -rf .venv
__pycache__` and rebuild.

**`gauntlet review` diffs against git, not the ledger.** The registry stores hashes, not content, so
a "what changed" diff needs another source. Without a committed version it says so plainly rather
than guessing — but the diff is unavailable for uncommitted or untracked files.

## Planned work

**Not yet built, in rough priority order.**

- **The test API boundary gate.** Step definitions should only reach the system through a stable
  `tests/api/` layer — an AST check on imports. This was designed in Phase 4 and never implemented,
  which makes it exactly the kind of rule that decays: currently it can only live in a prompt.
- **Root-cause diagnostics** across the gates, per the known issue above.
- **`init` scaffolding** so a new project is green by construction.
- **A second language adapter** (C#: coverlet, Roslyn, Stryker.NET, Reqnroll) — what turns the
  adapter seam from a claim into a fact.
- **A dashboard** over the event log: live gate progress, the approval inbox, one-click review. The
  log and the JSON contract exist so this can be a client rather than a rewrite.
- **Real-world validation.** Everything here has been proven on one small project. The tool has not
  yet been used to build something someone actually wanted, which is the next thing being done with
  it.

## Roadmap

### v1 — a usable single-agent harness for Python (where this is now)

Ten gates, the approval ledger, hooks, status and review, the event log. Proven on two projects:
this repository, and an FNOL intake service built end to end under the gates. What remains for the
v1 line is polish rather than capability — see `BACKLOG.md`.

### v2 — the workspace

The bottleneck today is not enforcement, it is the human's surface. Setup is a dozen manual steps;
review is a terminal walk; "what is waiting on me" is a command you have to think to run. A
workspace — live gate progress, the approval inbox, diffs in context, one-click approve — is the
next real gain, and the event log and JSON contract exist so it can be a *client* of the existing
tool rather than a rewrite of it.

### v3 — the substrate for orchestration

Multi-agent harnesses describe a fixed workflow as a state machine: themes to stories, stories to
specifications, specifications to code, code to cleaned, cleaned to hardened, hardened to accepted.
That structure needs an answer to *"has this transition actually happened?"* — and a supervisor
agent that answers by inspection inherits exactly the prompt decay the gates exist to eliminate.

Gauntlet already answers most of those questions deterministically. A state's exit criteria is a set
of gates; a human-in-the-loop state is an entry in the approval ledger; the event log is the
observability substrate, and it records real per-gate durations, which is what a simulation of such
a workflow would need in order to jitter anything meaningfully.

Three additions would make that substrate explicit:

- **Work-item identity** — an ID threaded through every event, so the log is per-story rather than
  per-project.
- **Named gate profiles** — `[profiles] cleaning = [...]`, so a workflow state's exit criteria has a
  name rather than an ad-hoc gate list.
- **A transition query** — which profiles currently pass, as JSON.

That is deliberately *not* orchestration. Scheduling, worktrees, role prompts, and handoff protocols
belong to whatever sits on top. The claim here is narrower and, hopefully, more durable: a workflow
engine is only as trustworthy as its transition predicates, and deterministic predicates are what
this tool makes.

### Also planned

A second language adapter (C#: coverlet, Roslyn, Stryker.NET, Reqnroll) — what turns the adapter
seam from a claim into a fact — and broader agent support beyond Claude Code's hooks, for which
`gauntlet loop` is already the generic fallback.

## Credits

The methodology is Robert C. Martin's ([@unclebobmartin](https://x.com/unclebobmartin)) — the CRAP
ceiling, the complexity limit of 6, the acceptance-pipeline structure, and the premise that the
implementation is the agent's business and the metrics are yours. Reference implementations:
[swarm-forge](https://github.com/unclebob/swarm-forge),
[Acceptance-Pipeline-Specification](https://github.com/unclebob/Acceptance-Pipeline-Specification).
Gauntlet is an independent implementation of the ideas, not a port of his tools.

## License

MIT
