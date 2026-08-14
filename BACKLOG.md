# Gauntlet — Backlog

Known defects and planned work, with the evidence behind each. Everything here came from building
things with the tool rather than from testing the tool itself.

Sources: the Gauntlet build, the `gauntlet-demo1` walkthrough, phase 1 of ClaimGate (an FNOL intake
service built end to end under the gates), and the v2 design read.

**Open work is ranked by severity.** Fixed items are summarized at the bottom so the reasoning is not
lost.

---

## 1. Four contract defects — the machine-readable output is wrong

**Severity: high.** These affect every consumer — CI today, the v2 workspace tomorrow.

Found by a design session reading the source with intent to *consume* it. None was found by building
with the tool, which is a useful thing to know about what each activity surfaces.

- **`status --json` reports `passed: false` when the gates never ran.** The human renderer correctly
  says "not run"; the JSON says the project is failing. `Status.passed` is
  `bool(self.gates) and all(...)`, so an empty result set reads as failure. It should be `null`.
- **`gate.finished` events omit `vacuous`.** Added to `GateResult` and never threaded into the event
  payload, so the report and the event stream disagree about the same run. A consumer tailing events
  cannot tell a real pass from a pass that measured nothing — the exact distinction `vacuous` exists
  to make.
- **`approval.needed` never fires for mutants.** `_emit_approval_needed` filters to the `protect` and
  `acceptance` gates and to diagnostics whose symbol is `unapproved`, `modified`, or `missing`.
  Surviving mutants carry a function or scenario name as their symbol, so the inbox stream misses the
  item type that most needs human judgment.
- **`check --json` emits plain text under lock contention.** The run-lock message is written as
  English and exits 0, so a JSON consumer gets unparseable output and a success code.

**Also inconsistent:** `spec approve` accepts no `--reason` or `--reviewer`, while `mutant approve`
requires a reason. The ledger has fields for both and the spec path silently leaves them empty.

**Fix.** Five small, independent changes, each with a test. Scheduled as the second phase of the audit
branch, separated from the documentation pass so the no-behaviour-change discipline stays intact.

## 2. Mutation cost is unmanaged

**Severity: high.** It is the difference between a gate people run and a gate people disable.

Acceptance mutation on four small feature files: **117 seconds**, on every Stop hook. Code mutation on
this repository's own source: **87 minutes** for 3,752 mutants, because its tests spawn subprocesses.
ClaimGate's pure domain package: 3 seconds for 109.

**Fix.**

- Default `mutation_sample` to a non-zero value for the acceptance gate rather than "all", and
  document `scope = "changed"` as mandatory rather than merely default.
- Report elapsed mutation time in the gate's `actual`, so the cost is visible before it is painful.
- Consider caching: a mutant whose locator and signature are unchanged since the last green run,
  against unchanged bindings, does not need re-running.

## 3. Per-file coverage is noisy on framework code

**Severity: medium, and imminent.** `per_file_min` works well on a pure domain package and badly on
route handlers and adapters full of framework boilerplate. ClaimGate phase 2 introduces FastAPI and a
database and will hit this immediately.

**Fix.** Per-directory thresholds, or document the pattern plainly: strict on the domain,
aggregate-only elsewhere.

## 4. mutmut is fragile in a working tree

**Severity: medium.** Inherited rather than ours, and mitigated but not solved.

It copies the source tree with a plain `copy2`, which dies on a dangling symlink — an Emacs lock file
is exactly that. It also leaves a `mutants/` directory that collides with pytest collection. Both now
produce a `doctor` warning and a translated gate error. The underlying fragility remains and belongs
in the documentation rather than behind more patches.

**Also:** mutmut mutates string literals, so error messages that no test asserts on surface as
survivors. On a message-heavy codebase this is noise needing suppression patterns or many approvals.

## 5. A copied project directory is silently broken

**Severity: low, but expensive when it happens.** Virtualenvs and `__pycache__` embed absolute paths,
so a copied directory fails with import errors naming the *original* path. Cost about twenty minutes
to diagnose on `gauntlet-demo1`.

**Fix.** Documented in the README. A `doctor` check — does any `__pycache__` reference a path outside
this project — would turn it into a sentence, though the detection is a little speculative.

## 6. `gauntlet review` diffs against git, not the ledger

**Severity: low.** The registry stores hashes, not content, so a "what changed" diff needs another
source. Without a committed version the tool says so plainly rather than guessing — but the diff is
unavailable for uncommitted or untracked files.

## 7. Warn when a spec asserts on a value it was given

**Severity: low.** ClaimGate's queue-routing scenario takes `severity` as a `Given` and asserts it as
a `Then`. Mutating that cell changes the input and the expectation together, so it is structurally
unkillable.

Downgraded after investigation: the same swap on rows *without* an overriding flag died correctly, so
the pattern did not cause a false pass. A cheap lint — flag any Example column referenced by both a
`Given` and a `Then` step in one scenario — remains worthwhile.

---

## Fixed

Kept because the reasoning is worth more than the diff.

**Acceptance mutation picked alternatives that could not discriminate.** ClaimGate's first full run
produced 41 surviving mutants, all 41 equivalent: zero real findings, 94 seconds, 41 approvals
required. The cause was swapping a cell for another value from the same column, which usually landed
on a row with the same expected outcome. Fixed by preferring a value from the row that differs most
elsewhere — in practice a row whose expectation differs. On the same feature set: **41 survivors down
to 4, with 13 mutants becoming killable.** Runtime rose from 94s to 117s, because dying mutants need
a full failing run, which is why item 2 above matters more now than it did before.

**The tool could not tell you what it was not doing.** Three incidents, months apart: ClaimGate ran
with 7 of 10 gates for an entire phase; the first demo session ran with both hooks dead and looked
perfect; absent mypy once parsed as "no findings". Fixed by a `vacuous` flag distinguishing "passed"
from "had nothing to check", by `status` and `doctor` naming configured-but-disabled gates, and by a
`doctor` check that verifies the hook path and version end to end.

**Gates reported downstream symptoms instead of causes.** A brand-new project failed `gauntlet check`
immediately after `gauntlet init` with three errors, none naming the real problem — an empty `src/`.
Fixed by `init` scaffolding a green baseline, by the static and complexity gates naming an empty
source tree directly, and by coverage distinguishing "the tests gate did not run" from "it ran and
measured nothing".

**Concurrent runs corrupted each other.** A Stop-hook run reported a failing scenario that did not
reproduce; an agent-initiated `check` was finishing at the same moment. All runs share the `.gauntlet`
artifacts. The overlap is designed in — `CLAUDE.md` tells the agent to run `check` before declaring
done, and the Stop hook fires *when* it declares done. Fixed with an advisory lock; a second
concurrent run exits 0 with a message rather than interleaving. A gate that occasionally reports a
failure that is not real is worse than a missing gate.

**The test API boundary existed only in a prompt.** Designed in Phase 4, never implemented, and the
config key shipped anyway. Built as the `boundary` gate — an AST check on step-definition imports —
and it caught eight violations on its first run against ClaimGate. See below.

---

## Confirmed working — do not regress

**Code mutation finds real bugs that coverage cannot.** ClaimGate had 122 tests and 100% line and
branch coverage. Mutation found two genuine gaps: an untested `None` branch in the inception check,
and an `or`/`and` guard where a non-theft loss under $500 would have been misclassified as low
severity.

**Mutation testing finds untested boundaries.** On the demo project it identified four thresholds
where no test used the exact boundary value — 50,000, 90 days, 1,000 — all hidden behind 100%
coverage.

**A rule with no gate behind it decays — measured.** ClaimGate's kickoff prompt required a test API
boundary in its ground rules. The agent acknowledged it and then wrote eight direct imports of the
production package across four step files. Every other rule in that prompt that a gate enforced was
followed; the one rule with nothing behind it did not survive a single session.

**The equivalent-mutant ledger works.** Classify once, with a reason and a reviewer; the judgment
persists and lapses automatically when the surrounding case changes. Used in anger on both projects.

**The protect gate catches real drift**, including changes made by routes the guard cannot see. The
`review` walk showing a diff before approval is what makes the approval meaningful.

**Advisory context does help capable models.** ClaimGate's agent ran `gauntlet check` itself 22 times
across the session, unprompted after the first, and never attempted to weaken a threshold. That is
not enforcement and should never be relied upon — but it is real, and cheap.

**The spec-change loop is sound.** The human requests a change, the agent edits, the gate reports the
spec as modified, the human re-approves.

---

## Open questions

- **Did the ClaimGate hooks actually fire during phase 1?** The session shows no blocking hook output
  at all — consistent with an agent whose code always passed the fast gates, and equally consistent
  with dead hooks. `doctor` can now answer this prospectively; it could not answer it then.
- **Is `gauntlet loop` usable with a real agent?** It has unit tests and a fake agent, and has never
  been run against a live model. The five contract fixes in item 1 would be a good first trial:
  small, unambiguous, independently testable.
- **How much of acceptance mutation belongs in the edit loop?** After the discriminating fix it is
  genuinely useful and genuinely expensive. CI-only is a defensible answer.
