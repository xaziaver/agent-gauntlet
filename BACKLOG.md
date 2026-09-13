# Gauntlet — Backlog

The live queue for agent-gauntlet, with the known defects and planned work behind it and the
evidence behind each. Everything here came from building things with the tool rather than from
testing the tool itself.

Sources: the Gauntlet build, the `gauntlet-demo1` walkthrough, ClaimGate (an FNOL intake service
built end to end under the gates through phase 3 and frozen at `prototype-1`), and the v2 design
read.

**The order of the tool changes is `gauntlet-findings.md`'s "Note for the v1 effort"**, realized
cost first, decided 2026-09-07 and written out 2026-09-11; this file cites it rather than restating
it. The findings route some forty entries here by name, and this is where they are picked up, one
entry per commit, each validated against the frozen tag. The seven numbered items further down were
written in August 2026, before the build, and are kept as recorded with a dated note each. Fixed
items stay at the bottom so the reasoning is not lost.

---

## Clean-up stage

During the build the harness was frozen and the work moved; now the work is frozen and the harness
moves. Before it does, the documents are made true, with the gated tree — `src/`, `tests/`,
`gauntlet.toml`, `gauntlet.lock.json`, `pyproject.toml`, `.claude/` — unchanged throughout:
`git diff --name-only a0ef78d HEAD -- src tests gauntlet.toml gauntlet.lock.json pyproject.toml .claude`
prints nothing after every part. One commit per part on `cleanup/documents`, each checked against
`origin` by the advisor and merged to `main` by the human. Nothing the findings cite is deleted.

G1. **Baseline.** *(Nothing to run; recorded 2026-09-12.)* `a0ef78d` is the harness that produced
    ClaimGate's verdict at `prototype-1`: its `src/`, `tests/` and `pyproject.toml` are byte-identical
    to `4fc5c34`, the last source commit before the tag. The verdict is committed in ClaimGate; the
    status section below records it. Tag `a0ef78d` as `prototype-1-harness` so the regression
    comparison names two tags **[human]**.

G2. **Document consolidation.** Six parts, in order.

G2a. *(Closed 2026-09-12 — `d49f259`.)* `doc-updates.md`, the August 2026 documentation plan the
    findings cite three times, committed as found (sha256 `66d587cd4f34357d`). Sections 1, 2 and 4
    are applied in G2d; section 3 is superseded by the v1 order.

G2b. *(Closed 2026-09-12 — `a8b9034`.)* `docs/session-prompts/ADVISOR.md`, the advisor start-up
    prompt (sha256 `2b7ae3793e0aea70`). Not in the coding agent's reading list.

G2c. *(This commit; its hash is recorded in G2d's status update.)* This file becomes the live queue:
    the clean-up stage, a reading table, a memoryless status section, and a dated note under each of
    the seven August items. Produced by a tested script with every anchor asserted unique and the
    result pinned by sha256.

G2d. `README.md` and `ARCHITECTURE.md` per `doc-updates.md` sections 1, 2 and 4, with two departures
    from section 1: "Planned work" and "Known issues" are kept and annotated in place — shipped, with
    the symbol, or open — because the findings cite both by name; and the "one small project" claim
    in "Planned work" is annotated, not deleted. After the roadmap replacement the C# adapter is named
    once, which is what section 4 asks.

G2e. `CLAUDE.md` gains session start-up, save-point and environment sections outside the scaffold
    markers; the text between the markers stays byte-identical to what `scaffold.upsert_block` emits.

G2f. `.gitignore` audited, last and alone: line 14, `.\#*mutants/`, split into the Emacs lock-file
    rule it was meant to be, the duplicate `.mutmut-cache` on line 15 removed, every rule annotated
    with what it hides. Checked by `git check-ignore -v .#x.py` naming a rule after and none before.

G3. **The harness moves against the frozen tag**, in the note's order, one entry per commit. Each
    entry gains a "Predicted effect on the regression subject" paragraph, ratified by the human,
    before its code moves. None of the eight entries the note orders has one yet (inventoried
    2026-09-12); the only such paragraph in the file is under "The Stop hook runs every gate after
    the first failure", the one entry already applied, and it is the model.

G4. **ClaimGate phase 4 opens on the harness G3 produces.** Not this repository's work.

## Not in the order

Open at `a0ef78d` per the inventory of 2026-09-12, and not sequenced by the note. **[human]** marks a
decision or a `gauntlet lock` only the human can supply.

- **This repository's acceptance gate is enabled with no `features/`.** `gauntlet.toml` declares
  `[gates.acceptance]`; the gate passes vacuously as "no feature files" on every run. Remove the
  table or add a feature — a gated change needing `gauntlet lock`, so not clean-up work **[human]**.
  Audit item O3 in `doc-updates.md`.
- **The hook exec form is verified for one hook only.** `.claude/settings.json` uses `command` plus
  an `args` array, the scaffold's own shape. ClaimGate's `PostToolUse` hook demonstrably fired under
  it (ClaimGate `docs/harness-findings.md`, the shell-written-file entry, observed 2026-09-08). There
  is no evidence either way for the `PreToolUse` guard, and `doctor` checks only that some hook's
  command names `gauntlet` (`doctor.py:199-208`). Audit item O5. Not urgent unless the guard is found
  dead.

## What to read

Every session reads `CLAUDE.md` and this file. Then, per item:

| Item | Read |
|---|---|
| G2d | `doc-updates.md` sections 1, 2 and 4; `README.md` "Known issues", "Planned work", "Roadmap"; `ARCHITECTURE.md` "Contracts you must not break" |
| G2e | `CLAUDE.md`; `src/gauntlet/scaffold.py` `upsert_block` and `guidance_block`; `tests/test_scaffold.py` |
| G2f | `.gitignore`; `ARCHITECTURE.md` "Known sharp edges" |
| G3, any entry | `gauntlet-findings.md` "Note for the v1 effort", then the entry in full; `ARCHITECTURE.md` "Contracts you must not break" and "Conventions"; `docs/GATES.md` for the gate touched |

## Status as of this handoff

**2026-09-12** *(the session; the commits carry local time, and the hook lines below are stamped
2026-09-13 UTC).* G2a and G2b are on `cleanup/documents` at `d49f259` and `a8b9034`, verified
against `origin` by the advisor; the human merges each part to `main` after verification. G2c is
this commit. Nothing under the gated tree has changed since `a0ef78d`. Next is G2d.

**The regression subject.** ClaimGate at the annotated tag `prototype-1`, commit `be87d38`. Its
`gauntlet.lock.json` is sha256 `61c2ac4d30025e8c`, 92 entries: 16 spec, 73 mutant, 3 config. The
engine at `a0ef78d` enumerates 1263 acceptance mutants over the sixteen specs, 808 of kind `example`
and 455 of kind `literal` (advisor-measured 2026-09-12 from `git archive prototype-1`). The sixteen
locked spec digests are listed in ClaimGate's `QUEUE.md` status section. The verdict every G3 change
is compared against is run `20260911T110451-2238600`, the tag's last stop-check, archived in
ClaimGate at `docs/queue-history/events-prototype-1.jsonl` (3912 lines, 836,642 bytes, sha256
`49395ea8c36d633f`): eleven `gate.finished` lines, all `passed: true`, `diagnostics: 0`, `error:
null` — protect 3/3 paths unchanged; static 0 findings; size worst function 25; complexity 6;
boundary 18 step file(s), 0 direct import(s); tests 966/966 passing; coverage line 100.0, branch
100.0; crap 6.0; duplication 0; mutation score 100.0 %, 757 killed; acceptance 16 spec(s), 73
reviewed-equivalent, 3736.757 s against ClaimGate's 7200 s Stop budget. An identical verdict means
those eleven tuples of `gate`, `passed`, `error`, `diagnostics` and `actual` unchanged, the lock
byte-identical, the subject's working tree clean after the run, and no other event-log difference
the entry's prediction did not name. A regression run is `gauntlet check` in a clean clone of the
tag, costing about an hour, with this repository's commit and an empty `git status --porcelain` here
recorded immediately before it: `gauntlet` is installed with `uv tool install --editable .`, so
this working tree is the tool, and a checkout here changes what every ClaimGate hook runs at once.

**This repository's own baseline.** Nine gates configured: protect, static, size, complexity, tests,
coverage, crap, duplication, acceptance; no `[gates.boundary]` or `[gates.mutation]`. The turn-end
stop-check after G2b, stamped 2026-09-13T01:29:28Z to 01:30:03Z, read by the human from
`.gauntlet/events.jsonl`: protect 3/3 paths unchanged; static 0 findings; size worst function 25;
complexity 6; tests 498/498 passing in 34.641 s; coverage line 96.54, branch 91.75 against floors of
95, 90 and per-file 80; crap 9.32; duplication 0; acceptance "no feature files" (vacuous).
Diagnostics 0 and error null on all nine. Stop hook budget 600 s; a full own-run is about 35 s by
the timestamps. The suite is `.venv/bin/pytest tests -q -p no:cacheprovider`; the `pytest` on PATH
is not the venv's and collects nothing. Branch coverage has 1.75 points of headroom over its floor:
a G3 change that adds an untested branch goes red here before it reaches the subject.

**The inventory of 2026-09-12**, read-only, agent-produced, from which this file was written.
Three source-line citations in the findings resolve at `a0ef78d` (`cli.py:151` and `cli.py:151-152`
exactly; `cli.py:235` has drifted to 232). "v1 item 2 (root-cause diagnostics)" at findings lines
863 and 1011 means `doc-updates.md` section 3's item 2, which was never applied here; item 2 of this
file is mutation cost. `CLAUDE.md` and `.claude/settings.json` are byte-identical to the scaffold's
output. All three lock digests match. CI runs `uv run gauntlet check --json` on push to `main`, on
pull requests and on dispatch, and uploads `.gauntlet/`. The remote branches `audit` and
`v2-workspace` are both at `5b9c0b5`, 0 ahead of `main` and 26 behind. `docs/audit.md`, cited by
`doc-updates.md`, is in no commit.

---

## Items recorded before the ClaimGate build (August 2026)

Written 2026-08-14 against phase 1. Kept as recorded, each with a dated note; the findings route to
them by number.

## 1. Four contract defects — the machine-readable output is wrong

*(2026-09-12: all four present at `a0ef78d` — `status.py:62-63`, `runner.py:98-105`, `cli.py:124-130`,
`cli.py:69-71`; `spec approve` still takes only paths, `cli_specs.py:16-17`. "Scheduled as the
second phase of the audit branch" did not happen: `origin/audit` is at `5b9c0b5`, 0 ahead of `main`.
In the note's item 7.)*

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

*(2026-09-12: the build's answer is the note's items 1 and 2 — *The acceptance gate runs the entire
steps directory once per mutant* and *The stop-check records no tree hash* — not the sampling
default. `mutation_sample` still defaults to 0 at `gates/acceptance.py:47`; no cache exists. The
117 s below became 3736.757 s at sixteen specs, one whole-suite run per mutant.)*

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

*(2026-09-12: not borne out. No findings entry names `per_file_min`, and the tag's verdict is line and
branch 100.0 with FastAPI and a database in place. Kept as a prediction the build did not confirm.)*

**Severity: medium, and imminent.** `per_file_min` works well on a pure domain package and badly on
route handlers and adapters full of framework boilerplate. ClaimGate phase 2 introduces FastAPI and a
database and will hit this immediately.

**Fix.** Per-directory thresholds, or document the pattern plainly: strict on the domain,
aggregate-only elsewhere.

## 4. mutmut is fragile in a working tree

*(2026-09-12: holds; `doctor.py:147` and `172-173` warn. This repository's own `.gitignore` did not
ignore Emacs lock files — its rule was merged onto another line — until G2f.)*

**Severity: medium.** Inherited rather than ours, and mitigated but not solved.

It copies the source tree with a plain `copy2`, which dies on a dangling symlink — an Emacs lock file
is exactly that. It also leaves a `mutants/` directory that collides with pytest collection. Both now
produce a `doctor` warning and a translated gate error. The underlying fragility remains and belongs
in the documentation rather than behind more patches.

**Also:** mutmut mutates string literals, so error messages that no test asserts on surface as
survivors. On a message-heavy codebase this is noise needing suppression patterns or many approvals.

## 5. A copied project directory is silently broken

*(2026-09-12: holds; nothing in `doctor.py` checks `__pycache__` paths.)*

**Severity: low, but expensive when it happens.** Virtualenvs and `__pycache__` embed absolute paths,
so a copied directory fails with import errors naming the *original* path. Cost about twenty minutes
to diagnose on `gauntlet-demo1`.

**Fix.** Documented in the README. A `doctor` check — does any `__pycache__` reference a path outside
this project — would turn it into a sentence, though the detection is a little speculative.

## 6. `gauntlet review` diffs against git, not the ledger

*(2026-09-12: holds, `review.py:45-80`.)*

**Severity: low.** The registry stores hashes, not content, so a "what changed" diff needs another
source. Without a committed version the tool says so plainly rather than guessing — but the diff is
unavailable for uncommitted or untracked files.

## 7. Warn when a spec asserts on a value it was given

*(2026-09-12: no source counterpart. The related findings entries are "Acceptance mutation cannot
distinguish a deliberately inert value from an untested one" and the designed boundary "A
same-outcome column can be the rule, not a table defect".)*

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
  *(2026-09-12: for phase 3 the `PostToolUse` hook is evidenced firing; the guard is not. See
  "Not in the order" above.)*
- **Is `gauntlet loop` usable with a real agent?** It has unit tests and a fake agent, and has never
  been run against a live model. The five contract fixes in item 1 would be a good first trial:
  small, unambiguous, independently testable.
- **How much of acceptance mutation belongs in the edit loop?** After the discriminating fix it is
  genuinely useful and genuinely expensive. CI-only is a defensible answer.
