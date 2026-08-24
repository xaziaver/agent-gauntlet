# Gauntlet findings

Proposed changes to Gauntlet, the boundaries it deliberately cannot cross, and
the properties worth preserving — discovered by using it to build ClaimGate, an
FNOL intake service developed end to end under the gates. Not assumed, not
designed in from the start.

This document is the output of Gauntlet's own v1 backlog item: *"Build
something someone wants, under the gates, and fold what breaks back into this
list."* Entries in **Proposed changes** are meant to be lifted out whole and
routed, so each carries a destination.

Its counterpart is `docs/harness-findings.md` in the ClaimGate repository,
which carries only what someone using the current version needs: how the harness
behaves today, and technique. The split is by audience and it is deliberate — an
agent implementing under the gates should not be loading proposals for a version
that does not exist yet. When an entry here has an operational consequence for a
user of the current version, that consequence is restated there as behaviour,
without the cost history or the proposal.

**Gauntlet is deliberately NOT modified during the ClaimGate build.** The
harness and the work it gates must not move at the same time, or the gate
results stop meaning what they appear to mean. If a finding becomes genuinely
blocking rather than merely annoying, it is escalated, not worked around
quietly. One has: see "Renaming a spec orphans its approval."

## How to read this

| Section | What it is | What to do with it |
|---|---|---|
| Proposed changes | Things the harness should do differently | Route per each entry's **Routes to** field |
| Designed boundaries | Things it deliberately cannot do | Never "fix" these. They constrain anything built above Gauntlet |
| Properties to preserve | Things that work, and could be broken by accident | Check any refactor against these |

Every **Proposed changes** entry carries: what happened, why it matters, the
proposed change, what the gap cost us, **Routes to**, and a status. Grouped by
destination, sorted by realized cost within each group; realized cost outranks
near-miss cost.

Findings route to three places, not one. `BACKLOG.md` takes actionable work.
Gauntlet's own README section "What building this taught us" takes findings
whose value is narrative — evidence that the approach catches things, which is
what that section is for. Some route nowhere: designed boundaries stay here, and
process lessons live in ClaimGate's `harness-findings.md`.

## Proposed changes to Gauntlet

**Vocabulary note, 2026-08-16.** Entries written before 2026-08-16 use ClaimGate names that have
since changed. `_is_recent_inception` became `_evaluate_recent_inception` on 2026-08-09, in the same
commit that created it. `policy_inception_date` and the `inception_date` column became
`continuous_coverage_date` and `coverage_start`, and `NO_POLICY_INCEPTION_DATE` became
`NO_CONTINUOUS_COVERAGE_DATE`, in ClaimGate item 4d on 2026-08-15. References to `siu_flags.feature`
are historical and correct as written — the file was called that at the time, and several entries are
about the rename itself. The arguments in every affected entry are unchanged; only the names moved.

A findings document that cites the gated project's internals accumulates that project's vocabulary
drift, and no sweep of the gated project will ever reach it — the names crossed a repository boundary
and nothing followed them. The dating convention ClaimGate adopted, naming a symbol only as a
locating aid with a verified-on date, applies here with more force rather than less, because the
distance between the two repositories means nothing will ever fail to tell you.

**Vocabulary sweep, 2026-08-22.** Re-run against ClaimGate at `origin/phase2/5a-carrier-configuration`.
Nothing in this document is wrong; two references now name things that no longer exist in the gated
project, and both entries are about historical events and are correct as written.

- The **$500 theft severity threshold**, cited under "Approval reasons go stale silently where the key
  does not" and under Designed boundaries, "Code mutation cannot find a guard no test exercises", was
  deleted in ClaimGate item 4c on 2026-08-13 together with `_is_low_severity_theft`,
  `THEFT_LOW_SEVERITY_THRESHOLD`, the `low` severity band and the `fast_track` queue. A reader who goes
  looking for the threshold will not find it.
- **`AU-7654321`**, cited under "Renaming a spec orphans its approval and leaves a dangling key", was
  renamed to `HO-7654321` in item 4a on 2026-08-13; the recognized policy-number prefix set then became
  caller-supplied configuration in item 4j on 2026-08-18, with `POLICY_NUMBER_PATTERN` reduced to
  shape-only. That entry is about the rename itself.

Checked and clean: no entry cites the injured-party model field names item 4g renamed on 2026-08-17,
nor the carrier names and NAIC company and group codes ClaimGate removed on 2026-08-17. Ledger counts
quoted inside entries were not re-verified against the current ledger this session.

**Vocabulary sweep, 2026-08-23.** Re-run against ClaimGate at `origin/phase2/5b-jurisdiction-date`
(`12dbb48`). `_evaluate_recent_inception`, `continuous_coverage_date`, `POLICY_NUMBER_PATTERN` and
`NO_CONTINUOUS_COVERAGE_DATE` all still exist and are cited correctly. ClaimGate item 5b added
`features/jurisdiction_date.feature`, `resolve_jurisdiction_date` and
`JURISDICTION_TIMEZONE_UNRECOGNIZED`, and renamed nothing. Item 5a landed the same day and added
`features/carrier_configuration.feature`, `src/claimgate/domain/carrier_configuration.py`,
`MISSING_REQUIRED_CONFIGURATION` and `MALFORMED_REQUIRED_CONFIGURATION`, again renaming nothing. No
entry below went stale by rename this session.

One entry did go stale by *measurement* rather than by name — see the 2026-08-23 annotation under
"A ragged Examples row parses silently and under-generates mutants". A name sweep will never catch
that kind of drift: the words in the entry are all still correct, and the advice they add up to
became wrong. When a measurement recorded on the ClaimGate side changes what an entry here should
conclude, nothing connects the two.


**Vocabulary sweep, 2026-08-24.** Re-run against ClaimGate at `origin/main` (`afb35a0`, item 5c
merged). Item 5c added `features/notice_intake.feature`, `src/claimgate/shell/` (`notice_intake.py`,
`store.py`), `src/claimgate/domain/carrier_identity.py`, and `tests/shell/`; two scenario titles in
its own feature file were corrected during drafting, before anything cited them. Nothing this
document cites was renamed or removed. Sweep clean.

### v1 — finish line

#### The blast radius of a spec change cannot be measured before making it

**What happened.** Deciding item 4c required knowing what the edit would do to
the approval ledger before the edit existed. There is no CLI path to that.
`gauntlet check` reports mutants only for the spec on disk, and only after the
approval stage passes — so learning the cost of a change requires making it,
locking it, and running the gate, by which point the approvals have already gone
stale. The figures that drove the decision (92→90 mutants; 7 of 13 approvals
needing re-review; 8 for a full vocabulary rename versus 3 for a surgical one;
zero non-discriminating substitutions after the theft rows moved to
standard/standard) were all obtained by importing `gauntlet.acceptance.gherkin`
and `gauntlet.acceptance.mutation` directly and running them against candidate
file contents held in memory.

**Why it matters.** This is the third distinct reason this project has had to
import the gate's own mutation source and bypass the CLI — after truncated
review output, and after the approval stage short-circuiting mutation entirely.
The first two are recovery workarounds for a gate that ran. This one is
different: it is a question the CLI cannot answer even when everything works,
because the tool only ever describes the present state of the tree. A reviewer
choosing between two spec edits has no supported way to cost either.

**What would address it.** A read-only preview command —
`gauntlet mutant preview <feature-path>` — that parses a feature file and prints
every mutant it would generate (scenario, locator, signature) without running
gates, touching the ledger, or requiring an approved spec. Pointed at a working
copy, it costs a spec edit before the edit is committed. It also incidentally
answers the truncated-review-output entry above, since a preview has no reason
to cap its output.

**Proposed change.** Add `gauntlet mutant preview <paths...>`, reusing
`acceptance.mutation.mutants()` unchanged, printing one line per mutant and
exiting 0 always. No new algorithm, no ledger access, no gate execution.

**What it cost us.** Nothing yet, because the workaround succeeded — but it
requires knowing the harness's internal module layout, which no user of the tool
should need. The alternative available to someone without that knowledge is to
guess, and a guessed blast radius was wrong by a factor of three and a half the
one time it was recorded from reasoning (2 approvals recorded in QUEUE.md item
4c; the real figure was 7).

**Routes to:** BACKLOG.md, v1.

**Status.** Open.

#### Mutation's own coverage-guided test selection goes stale on a test-only change

**What happened.** Not requested — found while verifying whether a unit test was still load-bearing
after an acceptance scenario was added to cover the same case. Removed one unit test
(`tests/unit/test_siu.py::test_recent_policy_inception_is_not_evaluated_when_no_threshold_configured`),
source unchanged, and ran `gauntlet check --gates mutation` against a `mutants/` cache built before the
removal: reported "score 100.0%, 181 killed" — identical to before the removal, as if nothing had
changed. Only after deleting `mutants/` entirely and letting mutmut rebuild from scratch did the true
number appear: 96.69%, 6 unresolved, all six in `_evaluate_recent_inception`'s
`NOT_EVALUATED`/`NO_THRESHOLD_CONFIGURED` return — exactly the branch the deleted test protected.
`mutants/mutmut-stats.json`'s `tests_by_mangled_function_name` mapping — mutmut's own coverage-guided
test-selection cache — still listed the just-deleted test as covering
`claimgate.domain.siu.x__evaluate_recent_inception` after the test was gone, consistent with mutmut
choosing which tests to re-run per mutant from that stale mapping rather than rediscovering it.

**Reproduction recipe**, run from a clean working tree with `mutants/` already built once against
the current suite (a plain `gauntlet check --gates mutation` if it doesn't exist yet):

```
1. gauntlet check --gates mutation --json      # baseline: score 100.0%, 181 killed
2. delete test_recent_policy_inception_is_not_evaluated_when_no_threshold_configured
   from tests/unit/test_siu.py (source untouched)
3. gauntlet check --gates mutation --json      # WRONG: still reports 100.0%, 181 killed
4. rm -rf mutants/
5. gauntlet check --gates mutation --json      # correct: 96.69%, 6 unresolved
6. git checkout -- tests/unit/test_siu.py      # restore, then rebuild clean before continuing
```

Steps 1-3-5 reproduced identically three times across two sessions (original discovery plus two
follow-up cycles run specifically to verify this recipe before writing it down). **Narrower claim than
originally drafted, corrected before this shipped:** the mirror direction — restoring the test without
clearing the cache and expecting the gate to keep reporting the stale 96.69% — was observed once in
the original discovery but did **not** reproduce on two follow-up attempts under controlled,
cache-cleared-first conditions; both times the very next run after restoring reported the correct
100% immediately, no cache clear needed. That direction is not asserted as reliable. Only the false
PASS on removal (steps 1-3) is confirmed reproducible.

**The case that actually matters: weakening, not deleting.** A deleted test changes the test count and
is visible in a diff by its absence. Ran the same recipe against a *weakened* test instead — same
function, same call, assertions dropped (`tests/unit/test_siu.py`'s
`test_recent_policy_inception_is_not_evaluated_when_no_threshold_configured`, changed from asserting
`.value == "NOT_EVALUATED"` and `.reason == NO_THRESHOLD_CONFIGURED` to calling
`compute_siu_indicators(...)` and asserting nothing — the exact shape of test CLAUDE.md instructs
agents not to write, "coverage of code that asserts nothing is worthless," and the one gate that exists
to catch it). Test count stays at 159; `pytest` reports `1 passed` for it, same as before, because a
test with no assertions trivially passes. Against the warm cache: "score 100.0%, 181 killed" —
unchanged, exactly as if the assertions were still there. Cleared `mutants/` and reran: "score 96.69%,
6 unresolved" — the identical true result as the deletion case, same six mutants, same function. This
is the more consequential half of the finding: it means the gate can be silently defeated by precisely
the failure mode it exists to catch, and unlike deletion, nothing about it is visible in a test count
or an assertion-free diff someone might skim past.

**Third scenario, now tested: a genuinely new test added for new code, evaluated for the first
time.** Previously left open, with the guess that a brand-new test covering code the cache has never
seen "would presumably force fresh collection." It does not, and "presumably" was again the word to
retract. During item 3's implementation — a commit adding `_resolve_notice_type_exclusion`, a
function the cache had never seen — a warm-cache run reported 99.06%, 2 unresolved, both survivors on
that function's `if notice_type == "INITIAL"` line (mutated to `"XXINITIALXX"` and to `"initial"`,
both "no test failed"). Impossible on its face: under either mutation every INITIAL candidate falls
through to the function's `raise ValueError`, so every unit test using INITIAL fails loudly. Clearing
`mutants/` and rerunning gave 100%, 213 killed, no survivors.

**This is the opposite direction from the confirmed case above, and the asymmetry is the point.**
Steps 1-3-5 confirm a false PASS: the cache reporting *better* than reality after a test-only change.
This instance is a false *survivor*: the cache reporting *worse* than reality after a source-adding
change. Only the conservative direction gets caught, because someone eventually asks why an
implausible mutant survived; nothing here rules out the dangerous direction on a source-adding
change, and the two are not symmetric in consequence. The narrow rule that follows is: **a mutation
score on a commit that adds a function is only meaningful from a cold run.** Note also how it
surfaced — the gate was *passing* at 99.06% against a 90% threshold. It was found by an agent judging
a green result implausible, not by anything failing.

**Does the acceptance gate's own spec-mutation share this exposure? Tested directly, not inferred.**
Weakened `tests/acceptance/test_triage_acceptance.py`'s `check_severity` step to `assert True` and
called `gauntlet.gates.acceptance.survivors_for` on `features/triage.feature` immediately after, with
no cache-clearing action of any kind: survivor count went 13 → 41 in that single call. Restored the
step to its exact original content and called it again, still no cache action: 41 → 13, back to
baseline. The acceptance gate's mutation mechanism is architecturally different from mutmut's — no
persistent cache directory; `run_acceptance` invokes `pytest ... -p no:cacheprovider` as a fresh
subprocess per mutant (`gauntlet/adapters/python.py`) — and behaves correctly here. Said cautiously
because "probably not" was exactly the wrong instinct about mutation caching until it was tested; this
one was tested and held up, twice, in both directions.

**Does gauntlet do anything about mutmut's cache today?** No. `adapters/python.py::run_mutmut` calls
`mutmut run <filters>` and nothing else — no `--no-cache` equivalent, no mtime check, no flag. It
fully trusts whatever incremental behavior mutmut applies internally.

**Why it matters.** A false PASS is categorically worse than a false failure for a gate that exists
specifically to catch tests that assert nothing: it is silent, and it is exactly the situation an agent
is in immediately after adding a test to close a coverage gap and re-running the gate to confirm — the
gate can report success without the new test having been consulted at all, if `mutants/` predates it.
It also corrects a claim made elsewhere in this document (see the correction note under "The coverage
gate reports a stale artifact as a current result" below) that mutation is immune to this class of
problem because it "genuinely re-executes... not because it was cached" — true of the subprocess
invocation, false of mutmut's own on-disk coverage-selection state.

**What would address it.** Cache invalidation keyed on test file content, not just source file
content — or, more simply, gauntlet forcing a clean `mutants/` rebuild whenever any file under the
configured test path is newer than the cache.

**Proposed change.** The mutation gate should detect whether any file under the mutation test scope
(`tests/unit/`, per `pyproject.toml`'s `pytest_add_cli_args_test_selection`) has changed since the
cached results it's about to rely on were produced, and clear or bypass the cache when it has — the
same freshness-check shape already proposed for the coverage gate's stale-artifact finding, applied to
mutmut's cache instead of `.gauntlet/coverage.json`. Concretely: `gates/mutation.py`'s `run` compares
the newest mtime under `cfg.tests` (or at minimum `tests/unit/`) against `mutants/`'s own build time
before invoking mutmut, and passes whatever cache-bypass mutmut offers (or does `rm -rf mutants/`
itself) when the tests are newer. The underlying staleness is mutmut's own behavior, so the real,
upstream fix belongs in mutmut — but the exposure is gauntlet's to close regardless, because gauntlet
is what reports the number and enforces the `min_score` threshold against it. A caller of `gauntlet
check` has no visibility into mutmut internals and no reason to expect the number it's given to depend
on when `mutants/` was last rebuilt.

**Consequence worth stating explicitly, not glossed over.** Every mutation score in this project's
history — every "100%, N killed" reported in every prior `gauntlet check` run across every prior
session — was produced against whatever `mutants/` cache state happened to exist at that moment, and
the gate's output gives no way to tell a freshly-computed number from a reused one; nothing in
`actual` or the diagnostics distinguishes them. This is not a claim that any specific past number was
wrong — most of this project's development added tests alongside source changes in the same commit,
which is a different situation from the isolated delete/weaken-only cases tested here, and no evidence
gathered says any particular historical score was false. It is a narrower, harder claim: the question
"was this specific reported score computed fresh or served from cache" cannot currently be answered
from the gate's output for any run, past or future, until the freshness check above exists.

**What it cost us.** A false pass that would have hidden a genuine 6-mutant gap in production code,
confirmed reproducible three times on deletion and reproduced again, identically, on weakening — the
more realistic and more dangerous of the two, since a weakened assertion changes neither the test count
nor the shape of a passing test run. Found only because a human's question ("what does the unit test
prove that the scenario doesn't") prompted verification from a clean state instead of trusting the
reported number — not by anything in the harness flagging it.

**Routes to:** BACKLOG.md, v1. Correctness, not cost — belongs as its own item rather than under mutation cost management. Highest-priority entry in this document: a gate that certifies a suite whose assertions have been removed.

**Status.** Open.

#### The acceptance gate re-runs every mutant on every check, and the green path now costs eight minutes

**What happened.** A passing `gauntlet check` on ClaimGate main measured the acceptance gate at
452.7s and 472.8s on consecutive clean runs — 48 mutants across 7 specs, one full suite execution
per mutant, re-executed from scratch although neither the specs nor the suite had changed between
the runs. The red path was measured the same day at 423.6s. The project's earlier records are
~150s, then ~230s, then 260.3s: the cost tracks mutant count times suite time and both only grow.

**Why it matters.** This is the recurring price of every stop event on a green tree, paid by the
hook loop without a human asking, and it scales with project size rather than with what changed.
The code-mutation gate has `--changed` filters; acceptance has no equivalent — an approved,
unchanged spec whose suite fingerprint is unchanged is re-mutated in full every time.

**What would address it.** Cache acceptance mutation results keyed on the pair (spec digest, suite
fingerprint), invalidating per spec; or a `--changed` analogue that mutates only specs whose digest
or bound step modules moved. The digests already exist in the ledger; the missing piece is a suite
fingerprint.

**What it cost us.** Roughly eight minutes per full check at current size, several times per
session, growing monotonically. No correctness cost.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

#### Interrupted mutation runs leave corrupted source

**What happened.** The acceptance gate mutates spec files in place during mutation testing and
restores them afterward. A `gauntlet check` run killed mid-mutation (a tool timeout, exit 143) left
a literal `"_gauntlet"` string injected into a step definition in `features/validation.feature`.
Caught by `git diff` before the next commit, but only because someone thought to look.

**Why it matters.** A corrupted spec file is indistinguishable, at a glance, from a real edit. If a
human trusts an approved-spec's hash without diffing after any interrupted run, a self-inflicted
mutation can slip through as if it were intentional.

**What would address it.** A clean working tree before any gate run, so a subsequent diff is
diagnostic rather than ambiguous; a longer default timeout for the acceptance gate specifically,
since it's the slowest gate by a wide margin; and ideally a restore-on-interrupt guarantee inside
the harness itself, so a killed process can't leave mutated content behind.

**Proposed change.** A restore-on-interrupt guarantee in the acceptance gate: if mutation testing is
killed (timeout, signal, crash) before completing, the harness restores every mutated file to its
pre-mutation content before exiting, rather than leaving partially-mutated content in the working
tree for the next `git status` to discover by chance. Pair with a longer default timeout for the
acceptance gate specifically, since it's the slowest gate by a wide margin and the most likely to be
killed mid-run.

**What it cost us.** A real corruption, not a hypothetical one — a literal `"_gauntlet"` string
landed inside a step definition in an already-approved spec file. It was caught only because a human
happened to run `git diff` before the next commit; nothing in the harness itself flagged it.

**Routes to:** BACKLOG.md, v1.

**Status.** Open.

#### Run pairing in the event log is unreliable in two directions

**What happened.** Reconstructing which `gauntlet check` runs had been killed required pairing
`run.started` to `run.finished` across the whole event log. Two separate asymmetries in `cli.py`
make that unreliable, and both were found only by reading the source after a pairing attempt
produced a wrong answer.

First, `check` emits `RUN_STARTED` at `cli.py:151` *before* calling `_locked_run`. When another run
holds the project lock, `_locked_run` catches `RunInProgressError`, echoes, and raises
`typer.Exit(EXIT_OK)` — so `_finish`, the only emitter of `RUN_FINISHED`, never runs. A lock-rejected
run leaves an orphaned `run.started` with the same shape as a run killed mid-gate. In this project's
log that produced 5 orphans in 59 seconds on 2026-08-13 alongside 4 genuine kills, and the two
classes are separable only by counting `gate.finished` events as a proxy: a lock-rejected run has
none, a killed run has one per completed gate.

Second, `RUN_STARTED` is emitted in exactly one place in the whole package — inside `check`.
`stop_check` (`cli.py:235`) runs the full gauntlet under the same lock and emits neither boundary
event, only the per-gate events the runner produces. Every Stop-hook run is therefore invisible to
any pairing keyed on `run.started`, and drops silently out of any run count taken that way. Two
separate analyses in this project undercounted gate executions for exactly that reason before the
cause was read from source.

**Why it matters.** The event log is the only durable record of what the harness actually did, and it
is what a reviewer reaches for when a spec file turns up modified or a gate result looks wrong. A log
whose runs cannot be paired reliably answers the question it exists to answer only with a heuristic.
The first asymmetry cost a full session's analysis, redone twice: once with a nesting-depth heuristic
that invented structure the log does not have, and once correctly by run id.

**Proposed change.** Two parts, neither a one-liner. For `check`, move the emit inside the lock:

```python
# check(), replacing cli.py:151-152
def _run() -> list[base.GateResult]:
    log.emit(events.RUN_STARTED, command="check", gates=selected, changed=changed)
    return runner.run_gates(ctx, cfg, selected, fail_fast, log)

results = _locked_run(root, _run)
```

That keeps `check()` at 19 lines against its own 25-line size gate. The second part is larger:
`stop_check` needs the same treatment plus a `_finish` call, and `_finish` currently hardcodes
`command="check"`, so it needs the command parameterised. Either change needs a test pinning it —
that a lock-rejected run emits no `run.started`, and that a stop-check run emits both boundaries — or
Gauntlet's own mutation gate has nothing holding the behaviour in place.

**What it cost us.** One session's event-log analysis produced a confidently wrong conclusion about
which runs had been killed, corrected only after the correlation id was found in the source. A
related claim — that a spec corruption had recurred — was asserted, then withdrawn, then confirmed
against the log by a third method. None of that would have been necessary if `run.started` meant a
run started.

**Why it is not applied.** Gauntlet is deliberately held still while ClaimGate runs against it.
agent-gauntlet is an editable install, so any change takes effect on ClaimGate's next gate run, and
ClaimGate's `docs/harness-findings.md` records the current behaviour as verified from source — the
harness change would land inside the gated project's own documentation. Apply after ClaimGate ships.

**Routes to:** BACKLOG.md, v1.

**Status.** Open, patch ready.

#### The acceptance gate short-circuits mutation on an approval failure

**What happened.** One dangling approval key (`spec:features/siu_flags.feature`, see below) made
the acceptance gate's approval-verification stage fail. That single failure returned early and
skipped the mutation stage entirely — for every spec, including `siu_indicators.feature` and
`triage.feature`, neither of which had any approval problem of their own. `gauntlet check` reported
only "1 unapproved or modified spec(s)" for the whole gate; nothing hinted that mutation testing
never ran.

**Why it matters.** Approval state and mutation state are independent concerns — whether a human has
signed off on a spec's text says nothing about whether its examples are wired to real behavior. Wiring
them so one failure hides the other converts "a rename left a stale key" into "we have no idea how
well-tested the other three specs are," for as long as the unrelated key sits there. On this project
that was the entire span between the rename and the human's manual fix — every `gauntlet check` in
between reported one line of diagnostic and gave no signal, positive or negative, about mutation on
any spec.

**What would address it.** Run the mutation stage regardless of approval state and report both
outcomes, or at minimum report explicitly that mutation was skipped and why, rather than silently
omitting it from the summary.

**Proposed change.** Decouple the two stages in `gauntlet/gates/acceptance.py`'s `_stages`: run
`_mutation_outcome` unconditionally (or gate it on baseline-passing only, not on approval), and
surface an explicit "mutation not run: N spec(s) unapproved" line when approval fails, instead of
returning before mutation is attempted at all.

**What it cost us.** 18 surviving mutants (7 on `siu_indicators.feature`, 11 on `triage.feature`) and
11 stale approvals sat undiscovered by any gate output for as long as the one unrelated key was
unresolved. Recovering them required importing the gate's own mutation source
(`gauntlet.acceptance.mutation`, `gauntlet.acceptance.gherkin`, `gauntlet.gates.acceptance`) and
running it directly against the real parsed feature files, bypassing the CLI entirely — the second
time this project has needed that exact workaround (see "A gate requiring human review must show the
human what to review" above, which needed it for a different reason: truncated output rather than a
skipped stage).

**Routes to:** BACKLOG.md, v1.

**Status.** Open.

#### An approved spec no test module binds reports every mutant as surviving, and the diagnostic asserts the opposite cause

**What happened.** ClaimGate item 5c's spec was approved before its step definitions existed. A
feature file joins the suite only through an explicit `scenarios(...)` call, so pytest never
collected it; the acceptance gate mutated the file anyway and ran the whole steps directory once per
mutant. Mutating a file no test reads cannot change the suite result, so every run passed and every
mutant was scored surviving — 24 reported, exactly the file's mutant count, 8/10/6 by scenario,
matching the per-scenario mutant counts to the digit. The diagnostic said "The scenario still passes
with these values changed, so it is not checking them," which is false in a specific way: the
scenario did not pass, it never ran. Its remedy then invited `gauntlet mutant approve` — in this
state the worst available action, since it would bank human equivalence judgments about a suite that
never executed, onto locators that all moved at the next spec amendment (measured: 0 of the 24
survived it), with no un-approve path.

**Why it matters.** The survivor count is the gate's central number and here it is uninterpretable
without out-of-band knowledge: "24 surviving" is the same string whether the suite ran and failed to
kill them or never ran at all. ClaimGate keys real decisions on that number — item 5c's
further-split condition fires "the moment any rule accumulates a survivor" — so a vacuous count
reads as a fired trigger. The gate's own vocabulary knows better than its behavior:
`survivors_for`'s docstring says "Mutants of one feature that *the bound scenarios* fail to kill,"
and the binding requirement it names is enforced nowhere. `_baseline_stage` checks only that the
suite passes; a suite that ignores the spec passes fine.

**What would address it.** Before mutating a feature, assert it contributes at least one collected
test. If it contributes none, fail — or mark the result with the `vacuous` flag `GateResult`
already carries and the gate already uses for the no-feature-files case — with a diagnostic naming
the missing binding, and suppress the survivor count entirely rather than reporting one that
carries no information.

**Proposed change.** A binding check in `gauntlet/gates/acceptance.py` between the approval and
baseline stages: collect once per feature (or parse the steps directory for `scenarios(...)`
targets) and report "spec approved but bound by no test module" as its own state, beside the three
the gate already distinguishes. The remedy for that state names the missing binding, not
`gauntlet mutant approve`.

**What it cost us.** One full mutation pass at 423.6s producing 24 survivors carrying zero
information; an approval landed on a spec whose review then reopened, so the approval was spent on
a digest that never reached implementation; and a near miss on 24 false equivalence judgments,
declined only because the count's vacuity had been established by measuring the mutant counts
independently first. The operational lesson recorded on the ClaimGate side — approve a spec at the
start of the session that implements it, not the end of the session that drafts it — exists to
route around this gap.

**Routes to:** BACKLOG.md, v1, beside "The acceptance gate short-circuits mutation on an approval
failure" — that entry is the same staging problem mirrored: there an approval failure hides
mutation state; here approval present with binding absent runs mutation vacuously and reports it as
real.

**Status.** Open. Not patched: Gauntlet is frozen for the duration of the ClaimGate project.

#### The coverage gate reports a stale artifact as a current result

**What happened.** The tests gate errored at collection — a spec rename had broken a binding file's
path, so no tests ran at all — yet the same `gauntlet check` invocation reported coverage at
100%/100% in 0.001s. `gates/coverage.py` reads `.gauntlet/coverage.json` off disk and runs no
subprocess of its own; the artifact was three commits old, written during an earlier run that
predated the rename, and nothing re-validated it against the run that had just failed to collect.
Mutation is not affected by this, and shouldn't be lumped in with it: `pyproject.toml` scopes
mutation's test selection to `tests/unit/` only, which never touches the broken binding file, so
`gates/mutation.py` genuinely re-executes `mutmut run` as a fresh subprocess every invocation — its
number held steady because the source hadn't changed, not because it was cached.

**Why it matters.** A green coverage number sat beside an uncollectable test suite. It failed safe
only because the tests gate was red in the same run — a human or agent scanning gate output top to
bottom would still see the overall failure. But the coverage line itself asserted a measurement that
did not happen: "nothing to measure" reported as "measured, found nothing."

**What would address it.** A freshness check against the current run — coverage.json's mtime (or a
run id embedded in it) checked against the tests gate's own run, with an explicit could-not-measure
result when the artifact predates it, rather than silently reporting a stale number as current.

#### The code-mutation gate's source scope is set outside Gauntlet, and narrowing it is invisible

**What happened.** Every structural gate scopes to `gauntlet.toml`'s `[project] src` — the tests
gate builds coverage with `--cov={ctx.src}` — and `gauntlet.toml` is guard-blocked, so an agent
cannot narrow it. The code-mutation gate is the exception. It shells out to mutmut, which takes its
source scope from `[tool.mutmut] source_paths` in the project's own `pyproject.toml`, a file the
protect gate content-hashes but the guard does not block. `gates/mutation.py`'s `scope = "changed"`
only layers module-name filters on top; it cannot widen what mutmut was pointed at. A module outside
`source_paths` yields no mutants at all. In ClaimGate that path is `src/claimgate/domain/`, so code
in any sibling package is mutated by nothing.

**Why it matters.** The narrowing has no signature in gate output, and the shape that occurs in
practice is the worse of the two:

- In a full run — the only shape ClaimGate ever issues, since no hook combines `--changed` with the
  mutation gate — the omitted module contributes zero mutants to a total dominated by the domain's.
  The score is unchanged and healthy, and nothing on screen indicates a module stopped being checked.
- In a `--changed` run where only the out-of-scope file changed, `_filters` is non-empty, mutmut
  finds nothing, and `score(0, 0, 0)` returns 100.0 through its `total == 0` branch. The gate passes
  and is *not* flagged vacuous: `_nothing_changed` sets that flag only when no files changed at all.
  `0 killed` in the summary is the only tell.

**What would address it.** Have the mutation gate assert that the language tool's configured source
scope covers `ctx.src`, and report a shortfall as a diagnostic rather than running inside the
narrower window and reporting that window's score as the project's. Separately, set `vacuous` when
`total == 0` for any reason, not only when nothing changed.

**What the gap cost us.** Nothing realized — it was found while deciding where to put a module
rather than afterwards. ClaimGate item 5b specified a timezone-resolution function that the design
called a shell concern rather than a domain one; placing it outside `src/claimgate/domain/` would
have exempted it from code mutation behind a green gate with no signal. It was placed in the domain
instead, on independent design grounds, and this gap is why the placement was verified rather than
assumed.

**Routes to.** `BACKLOG.md`.

**Status.** Open. Not patched: Gauntlet is frozen for the duration of the ClaimGate project.

**Realized, 2026-08-24, with a second facet.** Item 5c placed `src/claimgate/shell/` — two modules,
~340 lines of intake orchestration and persistence — outside `source_paths`, correctly, since the
design separates shell from domain. The predicted shape arrived exactly: the code-mutation gate
reports score 100.0%, 342 killed, and every one of those mutants is the domain's; the shell is
mutated by nothing, with no signature in gate output. The same item surfaced the test-selection half
of the delegation: ClaimGate's own config points mutmut's test selection at `tests/unit/`, and a
unit test there importing outside the mutated tree broke the mutation run's collection outright —
resolved by moving shell-layer unit tests to a new `tests/shell/` directory, i.e. the gated project
reshaped its test layout around the tool's config. Reported by the implementing agent and consistent
with the gate source (the gate runs bare `mutmut run`; every scope decision lives in the project's
`pyproject.toml`); the collection failure itself was not independently reproduced. The "What the gap
cost us" paragraph above should now read: realized, mildly — shipped shell code sits outside code
mutation behind a green 100.0%, on design grounds the entry anticipated.

#### The mutation gate reports one project-wide total with no per-module attribution

**What happened.** `gates/mutation.py::_summary` renders `score N%, K killed`, plus optional
unresolved, reviewed-equivalent and stale counts. There is no per-file or per-module breakdown, and
a `Diagnostic` carries a file path only for *survivors*. When everything is killed, the output
cannot answer "was module X mutated at all" — a module fully covered and a module silently outside
`source_paths` produce identical text.

**Why it matters.** That is precisely the question the entry above forces someone to ask, and the
gate already computed the number that answers it. It just isn't printed.

**What would address it.** Emit killed/total per module. At minimum, emit the set of modules that
produced zero mutants: that set is the signature of the scoping gap above, and it costs nothing to
compute.

**What the gap cost us.** To confirm one new module was inside the gate's scope, ClaimGate had to
clear the mutmut cache, re-run scoped to that module alone, restore state, and subtract against a
remembered prior total (217 + 15 = 232) — four manual steps and a subtraction standing in for a
number already in hand. Reported by the coding agent on 2026-08-23; the absence of per-module output
is read from source, the workaround itself is not independently verified.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

**Proposed change.** A freshness check against the current run, and an explicit could-not-measure
result when the artifact predates it.

**What it cost us.** Nothing directly; the cost is the false signal.

**Routes to:** BACKLOG.md, v1 item 2 (root-cause diagnostics). This is exactly that item's "nothing to measure" case reported as "measured, found nothing" — the clearest real instance of it found so far.

**Status.** Open.

**Correction (2026-08-09).** "`gates/mutation.py` genuinely re-executes `mutmut run` as a fresh
subprocess every invocation... not because it was cached" above is true of the subprocess, false of
mutmut's own internal state. See "Mutation's own coverage-guided test selection goes stale on a
test-only change" above: a fresh `mutmut run` subprocess can still consult a stale
`tests_by_mangled_function_name` mapping on disk and report an unchanged score when a test was
actually added, removed, or edited with no corresponding source change. Kept here as a pointer
rather than rewritten in place, per this document's own practice of correcting claims after
observation instead of erasing the original one.

**This is the third of the reasoning-not-verification claims this document has had to correct, after
the two on the dangling-key entry (once claiming a dangling key was undetectable, once assuming CLI
removal was possible).** The pattern is worth naming directly: every claim in this project written
from reasoning about how a tool must work, rather than from running it, has been wrong so far. None
has been right yet. That is not a reason to stop writing claims — it is a reason every one of them
stays provisional until it has actually been run, which is the discipline this document tries to
enforce on itself as much as on the harness it describes.

#### Retry loop burns attempts on non-agent-actionable failures

**What happened.** The Stop hook's retry-capped `gauntlet stop-check` fired repeatedly against an
acceptance-gate failure caused by a spec sitting unapproved, awaiting human review — observed at
12 attempts remaining, then 7, then 5, then 4, across separate stop events, with no change in the
underlying cause between them.

**Why it matters.** An unapproved spec is a queue state, not a gate failure the agent can act on.
No number of retries clears it — only a human running `gauntlet spec approve` does. Spending the
retry budget on a condition that can't change from the agent side wastes it against the failures
that actually are agent-actionable.

**Structural, not incidental.** ClaimGate's CLAUDE.md requires spec lock and implementation to be
separate commits, in that order, so the log shows the sequence rather than asserting it. That rule
guarantees a red tree between the two on *every* reopening: a spec drafted or awaiting approval,
with no step definitions behind it yet. The human-blocked state is therefore not an accident the
retry budget occasionally trips over — it is produced deliberately, once per reopening, by a
convention adopted for reasons that have nothing to do with the harness. Any project that separates
approval from implementation will generate this state on a fixed schedule. That changes the
priority: the cost is not "sometimes wastes retries," it is "wastes the full budget every time the
process works as designed."

**What would address it.** Gates should distinguish failures an agent can fix from failures
awaiting a human, and the retry loop should stop immediately on the latter rather than counting
down toward it.

**Proposed change.** The stop-check should classify each gate failure as agent-actionable or
human-blocked — "spec awaiting `gauntlet spec approve`" is always human-blocked — and stop retrying
immediately on the latter, rather than counting down a shared retry budget that treats both
categories the same.

**What it cost us.** Four confirmations across four sessions, the same underlying cause each time.
First: 12 retries burned (12 → 7 → 5 → 4, no change in cause between firings). Second: a further
twelve firings. Third: against a dangling approval key with no CLI remedy, which no agent action
could ever have cleared. The first three stopped only because an agent recognized the pattern
documented here and refused to keep retrying — not because the budget ran out safely or the harness
intervened. The fourth is the one that changes the picture: the loop ran its full six attempts and
terminated on its own ("Gauntlet gates still failing after 6 attempts — stopping the retry loop and
handing this to you"), against a spec awaiting human approval that was unclearable from attempt one.
So the mitigation observed in the first three sessions — an agent reading this document and
declining to retry — is memory-dependent, and it did not survive a fresh context. The loop does
terminate. It just spends everything first.

**Fifth confirmation, and it resolves which side drives the loop.** The first four left open whether
the retries were an agent choosing to try again or the hook re-firing on its own — this document
said to record that honestly rather than infer it. A later session settles it: the agent explicitly
stopped, reported a blocking design question it could not answer, and stated it was holding for a
human decision. The loop still ran four attempts against that held state. Whatever the agent decides,
the hook re-runs. That narrows the fix as much as it confirms the problem: guidance in a project's
own CLAUDE.md cannot prevent this, because agent intent is not what drives it. Only the harness can.

**The obvious workaround does not buy what it appears to.** `stop-check` accepts
`--max-attempts`, so a project can cap the loop from its own
`.claude/settings.json` without touching Gauntlet. Setting it to 1 was tried.
The hook still fired on every agent stop, reporting "after 1 attempts" and then
"after 2 attempts" in a single session, with a full gauntlet run behind each —
here roughly 2m17s apiece against a spec-draft state that no agent action could
clear. The cap bounds how many times the agent is bounced back with exit 2; it
does not bound how many times the gauntlet is executed, and the counter counts
stops rather than retries, so the message text describes something other than
what it names. A sixth session under the same cap reached "after 3 attempts"
in one sitting — three full runs against a spec human-blocked from the first —
confirming the counter is bounded by nothing, since it clears only on a passing
run and a human-blocked gate cannot pass. When the failure is human-blocked, the expensive thing is the
run, not the bounce. A cap on the wrong quantity looks like a fix and is not
one — which is a reason to classify human-blocked states properly rather than
to keep tuning the loop around them. The narrower version, if classification is
too large a change: when the previous run in the same session failed with only
human-blocked diagnostics and nothing has changed since, re-emit that verdict
instead of running again.

**Routes to:** BACKLOG.md, v1 item 2 AND v3. See the note for the v1 effort below — this adds a fourth category to that item's taxonomy, and the same distinction recurs in v3's transition query.

**Status.** Open.

**Addition, 2026-08-24.** ClaimGate wired the mitigation this entry implies —
`gauntlet stop-check --max-attempts 1` in `.claude/settings.json` — and it measurably works:
`should_escalate` is `count >= max_attempts`, so at 1 every failing stop-check escalates
immediately, no bounce ever occurs, and a session's stop events each cost exactly one gate run.
Four failing stop events in item 5c's amendment session cost four runs of the cheap approval-stage
failure and zero retries. One defect in the message, though: the session counter in
`.gauntlet/stop-attempts.json` resets only on a *passing* run, so the escalation text — "Gauntlet
gates still failing after 4 attempts — stopping the retry loop" — reported the fourth failing stop
event of the session as if a retry loop had run and been stopped. At max-attempts 1 no loop ever
ran. In a workflow where red-at-approval is the designed state for whole sessions, the number grows
monotonically and reads as thrash while describing the process working exactly as intended. The
classification proposal above stands; this annotation records that the blunt setting is a working
stopgap whose only cost is a misleading sentence.

#### The Stop hook cannot be scoped, and the prescribed workflow produces a phase where it cannot pass

**What happened.** ClaimGate's workflow, which Gauntlet's own design prescribes, commits the spec
lock before the implementation that satisfies it. During that interval the specification deliberately
describes behaviour the code does not yet have. Item 4e spent four turns in that state: the
acceptance specs asserted `LOSS_TYPE_UNRECOGNIZED` while `validate()` had no closed-set check, so the
`tests` gate reported 179/182 by construction.

The Stop hook ran the full gauntlet at the end of every one of those turns. Read `cli.py`:
`stop_check` takes exactly one option, `--max-attempts`, and calls `_select_gates("", cfg)` with a
hardcoded empty selector, which means every enabled gate. There is no `--gates` and no `--changed`,
unlike the `PostToolUse` hook, which scopes itself to `static,size,complexity --changed`. So each
turn paid the acceptance gate's ~156s, produced a 12KB persisted-output blob, and consumed a retry
attempt, to rediscover a failure that was the intended state of the work.

**Why it matters.** Two distinct problems share one cause.

The first is cost. There is no way to tell the Stop hook to run less, so a session that cannot pass
pays full price every turn. `--max-attempts` bounds how many times the agent is *bounced*, not how
many times the gauntlet *runs*.

The second is louder. The escalation message reads "Gauntlet gates still failing after N attempts —
stopping the retry loop and handing this to you," which frames an expected intermediate state as the
agent having failed to converge. On this project the agent was explicitly told the failure was
expected and to stop rather than fix it, and it complied — but the instruction had to come from a
human in the prompt, every session, because nothing in the tooling can express "the spec leads the
implementation right now." An agent without that instruction has been handed a failing gate and told
to act on the remedy, and the remedy for a failing acceptance test is to change the code. That is the
correct action in general and precisely the wrong one here, before the human has reviewed and
approved what the code is supposed to do.

**Config cannot reach it.** Three apparent levers all fail. Replacing `stop-check` with
`check --gates ...` in `.claude/settings.json` loses the exit-2 bounce semantics, per-session attempt
counting, the escalation `systemMessage`, and the `_locked_run` concurrency guard. Disabling gates in
`gauntlet.toml` is global and would weaken `gauntlet check` too. And both files are verified paths,
so either edit requires a `gauntlet lock` to re-baseline — the same protected surface the remedy-text
finding below is about.

**What would address it.** Two things, separable.

Give `stop-check` the gate selection `check` already has, so a project can decide what a turn
boundary is worth. This is the cheap half and it stands on its own.

The larger half: give the workflow a way to declare that the spec currently leads the implementation
— a marker the human sets when locking a spec and clears when the implementation lands. While set,
the Stop hook reports acceptance and tests as *expected-failing* rather than failing, does not consume
attempts, and emits a remedy naming the implementation work rather than suggesting the code be
changed to match. Gauntlet already knows the spec was approved more recently than the source it
governs; that ordering is in the ledger and in git, so the marker could be derived rather than
declared.

**Proposed change.** Add `--gates` and `--changed` to `stop-check`, mirroring `check`. Separately,
add a spec-leads-implementation state to the acceptance gate's reporting, derived from spec approval
postdating the last change to the code under test, that suppresses attempt-counting and reframes the
remedy.

**What it cost us.** Measured, not estimated: three sessions of item 4e, each burning the full
acceptance gate at every turn end, three escalation messages framing intended states as convergence
failures, and roughly 36KB of persisted output nobody read. The advisor eventually worked around it by
telling the agent to run `gauntlet check --gates protect,static,size,complexity,boundary,duplication`
by hand — which does not touch the Stop hook at all, so the full run still happened every turn. The
workaround addressed the symptom the human could see and not the one costing the time.

**Routes to:** BACKLOG.md, v1, beside "Retry loop burns attempts on non-agent-actionable failures."
That entry covers failures the agent cannot act on; this one covers failures the agent *can* act on
and must not, which is the more dangerous case because the remedy text is actionable and wrong.

**Status.** Open.


#### Mutant approval defaults to the widest scope

**What happened.** `gauntlet mutant approve` without `--scenario` applies to every surviving mutant in
the file. Running it that way swept two mutants from an unrelated scenario into an approval batch and
stamped them with reason text that did not describe them. Caught and corrected, but the default is
the dangerous direction: the narrow, explicit scope should be the default and the file-wide sweep
should require an explicit flag, because the failure mode is approving things nobody reviewed with a
justification that does not apply to them — precisely what the human-approval step exists to prevent.

**Why it matters.** A tool whose unscoped invocation is also its most dangerous one invites exactly
this mistake: reaching for the plain command and getting more than intended. The cost of that mistake
here was a wrong reason string, caught by a human reading the output; it could as easily have been a
mutant nobody actually reviewed getting the same rubber-stamp reason as ones that were.

**What would address it.** Invert the default: `gauntlet mutant approve` with no `--scenario` should
require an explicit `--all-scenarios` (or equivalent) to touch more than one scenario's survivors, so
the narrow, safe invocation is the one that requires no extra thought.

**Proposed change.** Invert the default: `gauntlet mutant approve` with no `--scenario` should
require an explicit `--all-scenarios` flag to touch more than one scenario's survivors, so the safe,
narrow invocation is the one requiring no extra thought, not the dangerous, wide one.

**What it cost us.** Running the unscoped command once swept two mutants from an unrelated scenario
into an approval batch, stamping them with a reason that didn't describe them. Caught and corrected
by a human reading the output, but the same mechanism could as easily have rubber-stamped a mutant
nobody had actually reviewed.

**Routes to:** BACKLOG.md, v1.

**Status.** Open.

#### Mutant approval keys are content-addressed on the whole row

**What happened.** Mutant keys embed every literal cell value in the example row. Changing
`true`/`false` to `TRUE`/`FALSE` across `triage.feature`'s end-to-end scenario's vocabulary — a
change to columns those approvals' judgments were never about — staled all 11 approvals on that
scenario.

**Why it matters.** The same mechanism that makes an approval self-verifying (change the row, the
judgment goes stale, correctly — see "An approved equivalent mutant is a regression test for its own
justification") also can't distinguish a change to the cell a judgment was actually about from a
change to any other cell in the same row. Over-invalidation is the safe failure direction, but it is
not free: it re-opens judgments nobody needs to re-litigate.

**What would address it.** Key on the mutated cell and the assertions it affects rather than the
whole row, or report staled approvals grouped by whether the mutated cell itself changed, so a
reviewer can tell "this judgment might actually be wrong now" from "this judgment's row got a
cosmetic edit" before re-reviewing either.

**Proposed change.** Key on the mutated cell and the assertions it affects rather than the whole
row, or report staled approvals grouped by whether the mutated cell itself changed.

**What it cost us.** 11 re-reviews arising from a cosmetic rename. Note this one as a trade-off
rather than a straightforward defect — over-invalidation is the safe direction, and the fix must not
weaken the self-verifying property.

**Addition, 2026-08-22 — a second over-invalidation channel, which the change proposed above does not
close.** The key is not the only content-addressed half of an approval. `mutants.subjects()` builds each
ledger entry as `{key_for(subject_key, m): m.signature.encode("utf-8")}` — the key is the locator, the
digest is the signature — so an approval is invalidated by a change to either. Demonstrated against the
engine on 2026-08-22 with a three-row table: renaming one row's value from `mold` to `water_damage`, in a
row carrying no approval at all, left the *first* row's locator byte-identical while changing its
signature from `fire->mold` to `fire->theft`, because `_discriminating_alternatives` sorts candidates by
`(-distance, value, value)` and the alphabetical tie-break moved. That approval reports as `MODIFIED`, not
`MISSING` — a different bucket, a different remedy, and a cause sitting in a row the reviewer never
touched.

Keying on the mutated cell rather than the whole row does not address this, because the churn is in the
digest rather than the key. Closing both channels means either making the substitution stable under edits
elsewhere in the column — selecting the alternative from the mutated row's own position rather than by a
value-ordered tie-break — or reporting the two channels distinctly, so a reviewer can tell a judgment
that moved from a judgment whose mutation changed underneath it. ClaimGate records the operational half
of this under "A mutant has two identities, and one of them moves when a neighbouring row changes"; the
proposal half had not crossed to this document until now.

**Routes to:** BACKLOG.md, v1. Trade-off, not defect — over-invalidation is the safe direction and the fix must not weaken the self-verifying property described under Properties to preserve.

**Status.** Open.

#### Acceptance mutation cannot distinguish a deliberately inert value from an untested one

**What happened.** Seven survivors on `siu_indicators.feature` are all threshold-literal
mutations, and they survive for three different reasons — a distinction only
visible after working through each one, since the gate reports them
identically.

**Two are deliberately inert** (lines 84 and 134): no policy inception date is
present, so the indicator resolves to NOT_EVALUATED with reason
NO_POLICY_INCEPTION_DATE regardless of the threshold's value. The threshold is
supplied precisely to prove the result comes from the missing input rather
than a missing threshold; isolating that variable is the scenario's purpose,
so mutating it correctly changes nothing.

**Four are margin, not inertness** (lines 147, 148, 167, 168): the threshold
is doing its job, but the example values sit far enough from it that a
plus-or-minus-one mutation cannot cross the boundary — 62 days against 45/46,
40 days against both 45/46 and 30/31. The boundaries themselves are proven in
dedicated boundary scenarios, which is where a one-day mutation does kill.

**One is guard-dominated** (line 118): the mutation alters the upper bound,
but the scenario exercises the lower one — the inception date postdates the
loss date, so the `0 <=` check rejects the negative interval before the upper
bound is consulted.

**Why it matters.** Supplying an inert value to isolate which fact actually drives an outcome is good
specification design, not a gap in the scenario. The gate cannot tell that apart from a value the
scenario simply forgot to check — both present identically as a surviving mutant — so it demands the
same human judgment for each. The equivalent-mutant approval then becomes the only record that the
inertness was deliberate rather than an oversight.

The original draft of this entry recorded four of seven as deliberately inert. That was wrong — two are. It came from a human reviewer reasoning about the scenarios from memory rather than working each mutation through, and was corrected when the agent producing the survivor breakdown checked the actual mechanics of each. Recorded because the error is the entry's own subject: a cluster of identical-looking survivors invites a single explanation, and the single explanation was wrong for five of the seven.

**What would address it.** None obvious, and possibly none wanted — the gate asking is arguably the
correct behavior; the alternative is the gate guessing at scenario intent, which is worse. Recorded so
the pattern is recognized rather than rediscovered per scenario: a reviewer seeing a cluster of
threshold-literal survivors should work through each one's actual mechanics before assuming a single
explanation covers them, since the three mechanisms above present identically.

**Proposed change.** None proposed.

**What it cost us.** Nothing measurable — this is a recognition aid, not a defect with a cost to
tally.

**Routes to:** Nowhere yet. Recognition aid; may belong under Designed boundaries once decided.

**Status.** Open, low priority. May be a designed boundary rather than a defect; recorded as a
proposed-changes entry rather than moved to that section because it hasn't been decided which it is.

#### A same-outcome enumeration guarantees one surviving mutant per row

**What happened.** Drafting ClaimGate item 4e, a closed set of fourteen loss types had to be
specified. The obvious shape, and the one the file's existing `notice_type` rule already used, is a
Scenario Outline enumerating the recognized values with a single column and one shared outcome —
every row accepted, no blockers.

Read `mutation.py` before drafting rather than after. `_swap` selects a replacement from
`_discriminating_alternatives`, which prefers a value drawn from the row differing most in the *other*
columns. In a same-outcome enumeration there are no other columns that vary, so every row is at
distance zero from every other, and the swap necessarily lands on another value from the same column —
another recognized value, in a row asserting the same outcome. The mutant cannot be killed. Not "is
hard to kill": cannot, by construction of the selection rule.

Confirmed against the ledger rather than inferred: all four of `validation.feature`'s
approved-equivalent mutants at that point were exactly the four rows of its `notice_type` enumeration,
sharing one reason. The pattern had already taxed the project once and nobody had named it.

Measured both candidate shapes with the engine before choosing. The same-outcome enumeration produced
thirteen guaranteed survivors, thirteen permanent ledger entries requiring human review, testing
nothing. Folding the recognized, unrecognized and absent cases into one outline with a varying outcome
column produced thirty-two mutants and zero survivors — every swap became discriminating, and every
one was killed by the implementation.

**Why it matters.** Enumerating a closed set with a uniform outcome is not an unusual or careless spec
shape. It is the natural way to write "these values are all accepted," it reads well, and it is what a
careful person produces unprompted — this project produced it twice. The tax is one permanent approval
per row, levied silently, and it scales with the size of the set being specified. Fourteen values cost
thirteen approvals; a fifty-value vocabulary would cost forty-nine.

The cost compounds with two findings already recorded here. Because `mutant approve` stamps every
survivor in scope with a single reason, all rows of an enumeration share one justification, which then
must stay true for all of them. And because approval reasons go stale silently where the key does not,
that shared justification is exactly the kind of prose this project has had to correct four times. So
the shape does not merely add entries; it adds entries of the most maintenance-hostile kind.

The information the approvals encode is real but thin: these enumerated values are behaviourally
identical inside the function under test. That is worth stating once, not once per row, and it is
worth stating in the spec rather than in the ledger.

**What would address it.** The engine could recognise the shape. When every row of an Examples table
shares an outcome across all non-enumerated columns, a swap within the enumerated column is provably
equivalent, and the gate could report it as a structural equivalence rather than a survivor awaiting
human review — one diagnostic naming the column, not one per row. That is a stronger statement than
the existing approval mechanism can make, because it is derived rather than judged, and it would not
decay.

Failing that, the gate could at least *name* the shape when it produces a run of same-signature
survivors from one column, so the human choosing between spec shapes learns the price before paying it
rather than after.

**Proposed change.** Detect uniform-outcome enumerations in `mutants()` and classify swaps within the
enumerated column as structurally equivalent, reported once per column. Alternatively, emit a
diagnostic when three or more survivors in one scenario share a mutated column and an outcome,
pointing at the mixed-outcome alternative.

**What it cost us.** Nothing realized on this project, because the shape was measured before the spec
was locked and the mixed-outcome form was chosen instead — thirteen approvals avoided, verified by
building the counterfactual and running it. But the four `notice_type` approvals already in the ledger
are this tax, paid earlier without anyone noticing, and they remain there.

**Addition, 2026-08-22 — a second construction, which the detection proposed above would not catch.**
ClaimGate item 5a produced a fully inert outline whose rows do *not* share an outcome. It carries `field`
and `value` columns and states its expectation inside the `Then` step as
`INVALID_REQUIRED_CONFIGURATION:<field>`, reusing a placeholder that also appears in a `Given`. The
outcome is therefore not a column at all. `_row_distance` scores only the Examples columns, so it cannot
see the expectation; and because the placeholder feeds the input and the assertion together, a swap in
`field` moves both and stays correct. Every swap in `value` lands on another malformed value, which is
malformed for every field. Measured 12 mutants, simulated 12 survivors — the first fully inert scenario
this project has produced.

The detection proposed above — every row sharing an outcome across all non-enumerated columns — returns
false here, because the rows genuinely differ in both columns present. The rule a detector needs is a
different one: **an outline is undiscriminated when its expectation is not a column of its own**, that is,
when every `Then` step is fixed text or is built from placeholders that also appear in a `Given`. That is
decidable from the parsed IR without evaluating anything, and it would have fired on this draft before a
lock rather than after.

Alternatives measured on the same rule before recommending one — mutant counts measured against the
engine, survivor counts simulated against the rule as specified, since no implementation exists yet:
promoting the expectation to its own column with one loading row gave 21 mutants and 7 survivors;
splitting by value type into three outlines, each pairing a valid value against a malformed one, gave 36
and about 5; carrying two reason codes with absent, malformed and valid rows in one table gave 39 and 1.
The sibling outline in the same file that had kept its expectation as a column measured 10 and 1. The
lever is neither the row count nor the column count. It is whether the expectation is one of the columns.

**Addition, 2026-08-23 — and having made the expectation a column, do not then add a loading row.**
The two halves of this advice work against each other, which nothing here said.
`_discriminating_alternatives` ranks candidates by `-_row_distance`, so it always prefers the most
different row, and an all-blank row differs from every other row in every column — the maximum
available. Once one exists it is a global attractor: **every cell in the table substitutes to blank**,
and no cell ever substitutes to a sibling value again.

Measured on ClaimGate's `carrier_configuration.feature` at `3ebea71`, a ten-row mixed-outcome table
plus one blank loading row. With the blank row: 33 mutants, of which 30 substitute to blank and 3 to
the `_gauntlet` marker, one or two of those three surviving. With the blank row deleted: 30 mutants,
**all thirty substituting to sibling values** — `claimant name -> claimant contact`,
`MISSING_REQUIRED_CONFIGURATION:claimant name -> MALFORMED_REQUIRED_CONFIGURATION:claimant contact` —
every one killed by the outcome column, and no survivors at all.

The two populations ask different questions. A blank substitution asks whether the rule fires when
nothing is named. A sibling substitution asks whether the implementation attributes the right outcome
to the right input, which is the question a mixed-outcome table exists to ask. So: **a loading row is
the fix for a same-outcome table and a regression in a mixed-outcome one.** It manufactures the
discriminating row a same-outcome table lacks; in a table that already discriminates through its
outcome column, it replaces all of that discrimination with weaker tests and adds survivors of its
own. Any detection this entry's proposed change implements should tell the two cases apart, because
the same remedy applied to the wrong one makes the table worse while raising its mutant count.

**Routes to:** BACKLOG.md, v1, beside "Acceptance mutation cannot distinguish a deliberately inert
value from an untested one." Related to "Mutant approval defaults to the widest scope" and "The
approval ledger has no per-mutant reason," both of which make this shape more expensive than the row
count alone suggests.

**Status.** Open.


#### The acceptance gate's remedy names a command that re-baselines a different gate

**What happened.** When `features/duplicates.feature` changed after approval, the acceptance gate
emitted: "This spec is the human's artifact, not yours: revert the change, or explain why it should
change and let the human re-approve it with `gauntlet lock`." `gauntlet lock` is not the
spec-approval command. `gauntlet spec approve` is — the CLI describes it as "Approve one or more
feature files. The deliberate human review step." `gauntlet lock` is described as "Approve the
current content of the verified paths," the protect gate's baseline and the counterpart to
`gauntlet verify`. Two different commands against two different artifacts, and the diagnostic names
the wrong one.

**Why it matters.** ClaimGate's CLAUDE.md instructs the agent to "act on the remedy rather than
guessing." That makes remedy text an interface rather than prose: something reads it and does what
it says. Doing what this one says would not approve the spec — the acceptance gate would still fail
— and it would re-approve the current content of the verified paths, which on this project are
`gauntlet.toml`, `gauntlet.lock.json`, and `.claude/settings.json`. Those are precisely the files
CLAUDE.md forbids the agent to touch, on the grounds that weakening a threshold is not a way to pass
a gate, and the protect gate is what makes that instruction enforceable rather than advisory. So the
remedy for a spec-drift failure, followed literally, re-baselines the guardrail against threshold
tampering. No malice is required; an agent doing exactly what it was told produces it.

**Reasoned, not observed.** The command was never run. The consequence above is derived from the two
commands' own help text and from the protect gate reporting `3/3 paths unchanged`, not from watching
it happen — and this project's own record is that claims written from reasoning about how a tool
must work, rather than from running it, have been wrong. What would confirm it: in a scratch clone,
modify a verified path, run `gauntlet lock`, and check whether `protect` then reports the modified
content as approved.

**What would address it.** Command names emitted in gate diagnostics should come from the same
source as the CLI's own command registration, so a rename cannot leave remedy text pointing
somewhere else. Short of that, a consistency check over remedy strings versus registered commands.

**Proposed change.** Correct the acceptance gate's remedy to name `gauntlet spec approve`, and add a
test asserting that every command named in any gate's remedy text resolves to a registered CLI
command — and, for gates that name one, that it is the command owning that gate's own artifact.

**What it cost us.** Nothing realized: caught while reading a gate diagnostic during review, before
anyone ran it. Recorded because the surface it sits on is the one the agent is explicitly told to
trust, and because the wrong command here is not inert — it writes.

**Routes to:** BACKLOG.md, v1. Also `doc-updates.md`'s section 4 consistency sweep, which covers
README-versus-table drift but not diagnostics-versus-CLI — a different axis from the "Ten gates"
observation in the note below.

**Status.** Open.

**Addition, 2026-08-24.** The defect is wider than the quoted message. Read from
`registry.describe` and observed in output the same day: the spec diagnostics are three
status-keyed messages — MODIFIED (the prose quoted above), MISSING (correct as written), and a
distinct not-approved prose, "is not approved. A human must review it and run `gauntlet lock`" —
and **two of the three name `gauntlet lock`**. The three-way distinction itself is right and worth
keeping (see "Acceptance failures are diagnosed as three distinct states" under Properties to
preserve); the fix proposed above must correct both messages, not one. A related over-claim on the
ClaimGate side — that new and modified specs share "one code path" and identical text — is being
corrected there; it reasoned from two observations to a mechanism the source contradicts.

#### The stale-approval remedy asserts one cause for a condition with two, and emits an incomplete command

**What happened.** ClaimGate item 4d renamed one Scenario Outline column (`inception_date` to
`coverage_start`) and three scenario titles in `features/siu_indicators.feature`. Six
approved-equivalent mutants had their locators change as a result, since a locator is built from the
scenario name and the example row's contents. The acceptance gate reported them as: "6 approved
equivalent mutant(s) no longer survive — the assertions got sharper, so these judgments are stale.
Remove them with `gauntlet mutant prune`". `mutant prune`'s own docstring says the same thing in the
same voice: "An assertion got sharper and now kills what a human once judged equivalent."

Neither statement was true. No assertion changed. No mutant was killed. Measured against
`gauntlet.acceptance.mutation.mutants()` at both refs rather than inferred: `triage.feature` yielded
90 mutants before and 90 after, `siu_indicators.feature` 38 and 38, and each of the six removed
approval keys paired to exactly one added key carrying an identical digest. The six judgments were as
valid after the rename as before. Their addresses moved.

**Why it matters.** ClaimGate's CLAUDE.md instructs the agent to act on the remedy rather than
guessing, which makes remedy text an interface. An agent told the assertions got sharper will go
looking for the sharpened assertion, and there is none to find. That much is only wasted effort. The
worse reading is the one the sentence actually licenses: if an assertion now kills what a human judged
equivalent, the judgment is obsolete and should be pruned and *not* reinstated. Under a rename the
opposite is correct — prune the dead key and re-approve the identical judgment at its new locator. The
two causes call for opposite second steps, and the diagnostic names only the first.

This is the same class as the sibling entry above, one level down. There the remedy named the wrong
command; here it names the wrong cause.

**Also, the command as emitted does not run.** `mutant prune` takes a required `feature` argument.
Pasting the remedy's `gauntlet mutant prune` verbatim fails with `Missing argument 'feature'` —
observed, not reasoned; it was run. It also prunes one feature per invocation, so a condition spanning
two features needs two calls, while the remedy reads as one action. The diagnostic knows which
features hold stale keys, since it lists them.

**What would address it.** The gate already holds everything needed to tell the two causes apart. Each
ledger entry carries a digest, and the digest of every current mutant is computable in the same pass
that finds the stale keys. If a stale key's digest matches a live mutant under a different locator,
the mutant was relocated, not killed; if it matches nothing, an assertion genuinely got sharper.
Diagnosing by cause also removes the need for a human to work out which case they are in, which on
this project was done by hand each of the four times it came up.

**Proposed change.** Split the stale-approval diagnostic into two reported states with distinct
remedies:

- *relocated* — the stale key's digest matches a live mutant at a different locator. Remedy: prune,
  then re-approve at the new locator, and say explicitly that the judgment itself stands. Name the new
  locator so the human can see the pairing rather than reconstruct it.
- *superseded* — no digest match. Remedy: prune, and do not re-approve without fresh review, because
  the assertion that now kills this mutant may be the correct outcome.

Emit `gauntlet mutant prune <feature>` with the argument filled in, one line per feature holding stale
keys. Correct `mutant prune`'s docstring, which asserts the superseded cause unconditionally.

**What it cost us.** Real but small. The advisor on this project handed the human
`gauntlet mutant prune` with no argument, taken from the remedy text rather than from the CLI, and it
errored on first run. Per-feature invocations followed. More significantly, the
relocated-versus-superseded distinction was worked out by hand — by pairing digests in a scratch
script — on a condition the gate could have classified itself, and the same manual reasoning was
repeated across items 4a, 4c and 4d.

**Routes to:** BACKLOG.md, v1, beside "The acceptance gate's remedy names a command that re-baselines
a different gate." Related to "Renaming a spec orphans its approval and leaves a dangling key" (v2) —
that entry covers the spec-level case of the same underlying fact, that approval keys are addresses
rather than identities. Related also to "Approval reasons go stale silently where the key does not,"
which is the inverse failure: there the key holds while the prose rots, here the key moves while the
judgment holds.

**Status.** Open.


#### `status --run` reports "nothing needs your approval" beside the survivors it just counted

**What happened.** `gauntlet status --run` on ClaimGate printed the acceptance gate's result — "7
spec(s), 24 surviving mutant(s), 69 reviewed-equivalent" — and, four lines below it in the same
output, "WAITING   nothing needs your approval." Twenty-four unreviewed survivors are precisely a
thing waiting on a human; the gate's own remedy in the same run says so.

**Why it matters.** The WAITING inbox is the surface that tells a human whether they are the
blocker. `status.py::pending()` computes it from config and spec approvals only, and its docstring
records the exclusion as deliberate: "Mutants are excluded on purpose: knowing whether one survives
requires actually running the mutation, which is not a cheap status query." That reasoning is
correct for bare `status` and stops holding for `--run`: `collect(root, cfg, gates)` receives the
gate results and `pending()` is computed without consulting them. The cheap-query justification is
being applied to the one invocation that already paid for the answer.

**What would address it.** When `collect` is handed gate results, fold unreviewed acceptance
survivors into `pending`. The no-gates path keeps its documented exclusion unchanged.

**What it cost us.** Nothing realized — caught on first read because the contradiction sat within
one screen. The cost shape if missed is a human reading "nothing needs your approval" as
permission to walk away from a red gate that is waiting on exactly them.

**Routes to.** `BACKLOG.md`, v1, beside the two remedy entries above — same family: the
human-facing surface contradicting the state it reports.

**Status.** Open.

#### Background steps are invisible to acceptance mutation entirely

**What happened.** Found while inventorying `loss_type`/`policy_number` vocabulary across
`features/` ahead of the vocabulary-rename reopening (`QUEUE.md` items 4a–4c), not requested.
Read `gauntlet.acceptance.mutation`'s `mutants()` directly rather than infer from behavior: it
iterates `feature.scenarios` only, calling `_example_mutants(scenario)` and
`_literal_mutants(scenario)` for each. `Feature.background` — confirmed, in
`gauntlet.acceptance.gherkin`, to be a `list[Step]` populated separately from any `Scenario.steps`
during parsing — is never passed to either function, so it is never a mutation target at all.
`features/duplicates.feature`'s Background (`Given an existing claim "CLM-1001" with policy number
"HO-1234567", loss date "2026-06-01", and loss type "fire"`) supplies those three values to all
fourteen scenario executions in the file, and none of the three has ever been mutated, in any
scenario, outline or standalone.

**A second mechanism that compounds it, in the same source file.** `_literal_mutants` also returns
early for outline scenarios (`if scenario.is_outline: return []`) — literal-text mutation only runs
against a standalone scenario's own steps. So a value hardcoded in an *outline* scenario's `Given`
line, outside its Examples table, is equally invisible: `duplicates.feature`'s "A follow-on notice
type is never compared..." outline fixes `loss type "fire"` and `policy number "HO-1234567"` in its
Given line, and neither is ever mutated, for the same underlying reason as Background — the line
just isn't reachable from either mutation path. Together, these two mechanisms are why a naive
"does this approval's row contain the value" count overstates the current ledger's exposure to a
vocabulary rename: of `duplicates.feature`'s 18 current approvals, only 10 are actually keyed to a
mutated loss_type/policy_number table cell (the other 8 look vocabulary-dependent by eye — their
scenario's `Given` text literally says `fire`/`HO-1234567` — but aren't, because that text was never
a mutation candidate). Across all four feature files the true count is 21 of 42 current approvals,
not 42 of 42. Getting that number right required reading both functions; reasoning from the feature
files alone would have overstated it by exactly the entries this finding describes.

**Why it matters.** The values a Background carries are structurally the ones a spec leans on
hardest — every scenario in the file inherits them, usually as the fixed point the rest of the
scenario is measured against (here, the existing claim everything else is or isn't a duplicate of).
Mutation testing exists to prove an example's values are wired to real behavior, and the Background
values are exactly the ones it never touches. A bug that only manifests when the existing claim's
own `loss_type`, `policy_number`, or `claim_id` is wrong would not be caught by acceptance mutation
at all, in any scenario that relies on Background rather than restating the value itself.

**What would address it.** Extend mutation generation to `feature.background`, using the same
literal-text approach `_step_mutants` already applies to a standalone scenario's own steps — a
Background step is not meaningfully different from a `Given` in a non-outline scenario, and the
existing regex-based literal matching (`LITERAL_PATTERN`) needs no change, only a call site.

**Proposed change.** `gauntlet.acceptance.mutation.mutants()` should also generate literal mutants
against `feature.background`'s steps — once per feature, not once per scenario, since Background
text appears once in the file regardless of how many scenarios inherit it — with a distinct
`kind` (e.g. `"background"`) in the locator, so a surviving mutant there reads as background-sourced
rather than being misattributed to whichever scenario happens to run first.

**What it cost us.** Nothing realized yet — found during inventory, before any rename landed. The
near-miss is real: the same content-addressed-locator mechanism already documented under "Mutant
approval keys are content-addressed on the whole row" would apply here too if it could, except worse
in the opposite direction — a Background value can change silently, with no stale-approval signal at
all, because no approval was ever keyed to it in the first place.

**Routes to:** BACKLOG.md, v1. Same family as "Mutant approval keys are content-addressed on the
whole row" and "Acceptance mutation cannot distinguish a deliberately inert value from an untested
one" — grouped with acceptance-mutation-coverage gaps.

**Status.** Open.

#### Step data tables are discarded by the Gherkin IR, so nothing downstream can reach them

**What happened.** Found reviewing ClaimGate item 5a's redraft of `features/carrier_configuration.feature`
(branch `phase2/5a-carrier-configuration`, commit `11fd18b`, 2026-08-22), which placed that item's
headline new rule — a refusal names every value it rejected, not the first — in a `Then` step's data
table. Read `gauntlet.acceptance.gherkin` rather than infer from behaviour: `Step` is `keyword`, `text`,
`line`, `column`, and nothing else. There is no field for a step-attached data table anywhere in the IR.
`Scenario` carries `steps` and `examples`; `Feature` carries `scenarios`, `background`, `tags`. A data
table under a step is discarded during parsing, silently and with no diagnostic, so `mutants()` cannot
reach it and neither can anything else built on the IR later.

Measured, not inferred. That scenario yields 5 mutants, every one a `"AAAA"->"AAAA"_gauntlet`
substitution on a step literal, none from its three-row assertion table. The pattern is not confined to
the new file: `features/validation.feature` uses `Then the blockers are:` in nine scenarios, and each of
the four standalone ones — "An absent policy number is a missing field, not a malformed one", "A
whitespace-only policy number is a missing field, not a malformed one", "A missing notice type is a
blocker", "An unrecognized notice type is a distinct blocker from a missing one" — yields exactly one
mutant, on its `Given`'s quoted literal. All nine of those expectations sit outside mutation.

**Why it matters.** This is the Background gap one step worse. A Background value at least survives into
the IR as `Feature.background`, so extending mutation to it needs only a call site; a data table is gone
before mutation runs, and the fix has to start in the parser. And where a Background carries inputs, a
data table usually carries the *assertion* — it is the shape a spec author reaches for precisely when an
expectation is too structured for one line, which is to say when it is the most load-bearing thing in
the scenario. A step definition that ignores its `datatable` argument, or asserts a hardcoded list,
survives every mutant in such a scenario and the gate stays green.

Nothing else covers it either. The spec digest hashes file bytes and moves for any edit, saying nothing
about whether the table is wired; the boundary gate walks the steps directory for absolute imports
rooted at a `src/` top-level name; code mutation mutates `src/`. So the agreement between a data table as
written and the parser that consumes it is held by review alone. ClaimGate's own convention makes that
concrete: its step reads `header, *rows = datatable` and zips with `strict=True` (verified in
`tests/acceptance/test_validation_acceptance.py`, 2026-08-22), so a table written without a header row
loses its first assertion row silently. The 5a redraft wrote one without a header against nine existing
tables that have one, and no gate could have said so.

**What would address it.** Retain step data tables in the IR, then mutate their cells with the machinery
`_column_mutants` already has. Unlike the Background gap, a call site is not enough — the data does not
exist by the time mutation runs.

**Proposed change.** Add a table field to `Step` (an `ExampleTable | None`), populate it in
`gherkin.parse`, and extend `_step_mutants` to generate cell mutants against it with a distinct `kind`
(e.g. `"table"`) so a survivor reads as table-sourced rather than being attributed to the step's literal
text. Failing that, at minimum `parse` should not silently discard a construct it cannot represent.

**What it cost us.** Nothing realized — caught in review before the spec was locked. The near-miss is the
whole point: had it locked, item 5a's central new rule would have shipped behind a green acceptance gate
with no mutation coverage of the one assertion that rule exists to make.

**Addition, 2026-08-23 — the remedy above has a trap, and this project walked into it the next day.**
The fix says to carry a structured assertion in an `Examples` column instead. ClaimGate did exactly
that and lost five mutants doing it. `_literal_mutants` returns early for outlines, so converting a
plain scenario into a one-row outline — the smallest edit that moves an assertion into an `Examples`
cell — forfeits every step literal in that scenario, and a one-row table has no alternatives, so each
cell yields a single `value+_gauntlet` substitution. Measured across three committed revisions of the
same scenario: 5 mutants as a plain scenario with the assertion in a data table, 1 as a one-row
outline with it in an `Examples` cell, and 6 as a plain scenario with the assertion **quoted in the
step text**, because `LITERAL_PATTERN` matches a quoted string in a step. The file-wide count rose
across that change, so nothing surfaced the loss.

A quoted literal in a plain scenario is the cheaper carrier for any assertion that fits on one line,
and a single-row outline is strictly worse than the plain scenario it replaces: it can only lose step
literals, and it cannot gain discrimination, because discrimination needs a second row. A diagnostic
on `is_outline and len(examples.rows) == 1` would catch it. Whatever addresses this entry should
carry that with it, or the fix will keep producing the regression.

**Annotated 2026-08-23: the recommendation in the paragraph above is wrong, and what falsifies it is
a measurement, not a rename.** "A quoted literal in a plain scenario is the cheaper carrier" holds
only if a quoted-literal mutant tests anything, and it does not — the marker lands outside the
closing quote, so the mutated step binds to no well-formed pattern and dies at step resolution
before the code runs. See "Every quoted-literal mutant is vacuous under a well-formed step pattern".

Re-reading the three measured revisions with that in hand inverts the ranking. The 6-mutant plain
scenario with the assertion quoted in step text is the *worst* of the three, not the best: all six
are vacuous. The 1-mutant one-row outline is the only one of the three whose mutant reaches the
code, because an `Examples` cell substitutes inside the quotes rather than after them. The counts in
the paragraph above are correct as measured; only the conclusion drawn from them was wrong, which is
why this is an annotation rather than a rewrite — the arithmetic is still the evidence.

**Routes to:** BACKLOG.md, v1, immediately beside "Background steps are invisible to acceptance mutation
entirely" — same family, and the two differ in fix boundary, which is worth carrying to whoever
implements them.

**Status.** Open.


#### Every quoted-literal mutant is vacuous under a well-formed step pattern

**What happened.** `LITERAL_PATTERN` mutates a quoted string in step text by appending the marker
*after* the closing quote: `"America/New_York"` becomes `"America/New_York"_gauntlet`. No step
definition written in the ordinary way — a captured group terminated by a closing quote, matched
with `parsers.re` or `parsers.parse` — can bind that line. pytest-bdd raises at step resolution, the
test fails, and the mutant is recorded as killed having never called the code under test.

Measured in ClaimGate on 2026-08-23 against all 45 step patterns across the four feature files
implemented at the time: of 82 literal mutants, 75 die at step resolution. Only numeric literals,
which mutate in place rather than by suffix, yield real tests.

Re-measured the same day when item 5a's `carrier_configuration.feature` was implemented, making five:
84 mutants in that file alone, 47 `literal` and 37 `example`, of which 34 of the 47 die at step
resolution and 13 numeric literals reach the domain. **Project total: 109 of 129 literal mutants
vacuous across five feature files, 84.5%.** That
figure is an overcount of an unknown size — see "`LITERAL_PATTERN`'s single-quote alternative
matches English possessives" below, which shows that some of what the engine counts as literal
mutants are not literals at all. `example`-kind mutants are unaffected — an `Examples`
cell substitutes inside the quotes rather than after them, so all 37 of those reached the domain.

The mechanism was confirmed at runtime for the first time during that item: one mutant was injected
by hand and the run raised `StepDefinitionNotFoundError`. Every earlier statement of this finding was
an argument from step-pattern analysis — that no house-style pattern *could* bind a marker-suffixed
line. This is direct observation of the death itself, and it closes the possibility that the pattern
analysis was simply wrong about some step somewhere.

**Why it matters.** This is a false-positive kill, and it is the most common kind of acceptance
mutant in the project. The gate counts them as killed, the score rises, and nothing distinguishes
them from mutants a real assertion caught. Every other entry in this document that reasons about
acceptance mutant counts is counting these too.

It also cannot be worked around honestly from the project side. Loosening a step pattern so the
marker-suffixed line binds would make the step accept text no specification ever wrote — a real
defect traded for a synthetic number. ClaimGate declined that and reshaped specifications instead;
see the 2026-08-23 instance under "Approval scope is coarser than the judgments it records".

**What would address it.** Mutate inside the quotes rather than after them, so the substitution
produces a well-formed step line that binds and then fails on the value. Failing that, a diagnostic:
a mutant that dies during step resolution is distinguishable at runtime from one that dies on an
assertion, and reporting the two separately would at least stop the count being read as evidence.

**What the gap cost us.** 75 of 82 literal mutants across four feature files test nothing while
counting as kills. Specifications were reshaped to route around it. And the defect went unrecorded
in this document for the length of the project — see **Status**.

**Routes to.** `BACKLOG.md`, v1, beside "A ragged Examples row parses silently and under-generates
mutants" — that entry's recommendation depends on the answer to this one.

**Status.** Open, and deliberately not patched: Gauntlet is frozen for the duration of the ClaimGate
project, so the harness and the work it gates do not move at the same time. Recorded here on
2026-08-23, late. The measurement had been sitting in ClaimGate's `docs/harness-findings.md` since
it was taken and the Gauntlet-facing half was never written down, so nothing in this document
referred to it and one entry gave advice that contradicts it. Worth noting as a process failure in
its own right: a finding recorded on the gated project's side only is invisible to whoever improves
the tool.

**Addition, 2026-08-24 — a third kill locus, between the two this entry distinguishes.** The
paragraph above separates death at step resolution from death on an assertion. Item 5c's step
definitions showed a middle case: a marker mutant that *binds* (the pattern captures to end of
line) and then dies inside the step body's own parsing — `_gauntlet` fed to a parser that splits
blocker pairs on `:` raises before any comparison with the implementation runs. That kill is
implementation-independent: it would score identically against a broken implementation, so it is no
evidence the scenario checks anything, and it is invisible in gate output for the same reason
resolution-deaths are. The same file's identity-column markers die by genuine assertion mismatch,
and only reading the step code tells the two apart. Any diagnostic built for this entry should
classify by failure locus — step resolution, step-body exception, assertion — not by the first two
alone; the cheap approximation is marking any kill whose exception is not `AssertionError`.

#### `LITERAL_PATTERN`'s single-quote alternative matches English possessives

**What happened.** `LITERAL_PATTERN` is `\"[^\"]*\"|'[^']*'|\b\d+\.\d+\b|\b\d+\b`. The second
alternative matches any span between two apostrophes. Gherkin written in ordinary English uses
possessives constantly, so two possessives on one line produce a literal mutant on the text between
them.

Measured by running the engine on a three-line scenario. `Then the notice's audit trail's first
entry is recorded` yields `'s audit trail'->'s audit trail'_gauntlet`; `And the carrier's adjuster's
queue doesn't change` yields `'s adjuster'->'s adjuster'_gauntlet`. A line carrying one apostrophe
yields nothing.

**Why it matters.** Three ways, in increasing order of cost.

They are noise in the ledger. Each one is guaranteed vacuous — no step pattern binds
`'s audit trail'_gauntlet` — and nothing distinguishes them from literal mutants on real quoted
values. Any count of literal mutants is inflated by however many are possessives, including this
document's own figure under "Every quoted-literal mutant is vacuous under a well-formed step
pattern".

They mislead the person reading a locator. `'s audit trail'` looks like a stray quote in the
specification rather than a quirk of the tool, and the natural response is to go hunting through the
feature file for a typo that is not there.

Worst, it charges for plain English. Avoiding it means writing "the audit trail of the notice"
instead of "the notice's audit trail". That makes this the third independent mechanism by which
Gauntlet reshapes the Gherkin under it — approval granularity, mutant vacuity, and now apostrophe
parsing — and the first that pushes a specification away from the way the person who owns the rule
would actually say it. A tool meant to keep specifications readable by domain owners should not tax
the possessive case.

**What would address it.** Require the single-quote alternative to be bounded by whitespace or a
line edge on both sides, so `'a value'` still matches and `notice's audit trail's` does not. Or drop
the alternative outright: the gated project's Gherkin quotes with double quotes throughout, and no
single-quoted literal appears in any of its six feature files.

**What the gap cost us.** A drafting session found it, diagnosed it correctly, and rephrased a
specification around it. That specification now carries a one-apostrophe-per-line constraint that
exists for no reason a later reader could guess from the file. Caught before it shipped, so no
phantom mutant reached a ledger.

**Routes to.** `BACKLOG.md`, beside "Every quoted-literal mutant is vacuous under a well-formed step
pattern" — same regex, and whoever fixes either should be looking at both.

**Status.** Open. Not patched: Gauntlet is frozen for the duration of the ClaimGate project.
Recorded 2026-08-23, the day it was found. Worth noting against the two entries above it, which were
both recorded late after sitting on the gated project's side: this one was found by the coding agent
and written into the gated project's own status file, where it would have stayed. Three findings,
three times the Gauntlet-facing half had to be carried across by hand. Whatever replaces that
handoff should not be a person remembering.

#### A ragged Examples row parses silently and under-generates mutants

**What happened.** Tested directly against the engine on 2026-08-22 rather than reasoned about. A
three-row Examples table under a two-column header, with the middle row's second cell omitted, parses
with no error and no diagnostic. That row's `Row.cells` has length 1; `_column_mutants` skips the missing
cell via `if column >= len(row.cells): continue`; the table yields 5 mutants where a well-formed one
yields 6. `_row_distance` compares with `zip(..., strict=False)`, so the short row is also scored against
its neighbours on the shared prefix only, which can change which alternative is selected for rows that
are themselves well formed.

**Why it matters.** The failure is silent in exactly the place this project does its measuring. A mutant
count is the unit of blast-radius estimation here, and a table that lost a cell to a bad paste produces a
count that looks plausible and is wrong low. The ledger gives no signal either: the short row's locator
(`...|example|loss_type|theft`) is shorter than its siblings' but perfectly well formed. This is not a
question about hostile input — the format is hand-maintained and its alignment is manual.

**What would address it.** Reject a row whose cell count differs from the header's, at parse time. A
Gherkin Examples table is not a ragged structure and there is no reading under which one is valid.

**Proposed change.** Validate row width against header width in `gherkin.parse` and raise `GherkinError`
naming the line, or surface it as an acceptance-gate diagnostic.

**What it cost us.** Nothing. No ragged row exists in ClaimGate's five feature files — checked. Recorded
before it costs anything, which is the cheap moment to record it.

**Routes to:** BACKLOG.md, v1, beside the entry above.

**Status.** Open.


#### Hook configuration has no home outside the file `init` rewrites

**What happened.** The only way to configure the Stop hook is the `args` array
in `.claude/settings.json` — `config.py` has no key for `max_attempts`, and
`stop-check` reads it only as a CLI option. But `scaffold.py`'s `merge_settings`
calls `_without_ours`, which identifies Gauntlet handlers by
`command == COMMAND` and drops them wholesale before re-adding them from
`claude_hooks()`. Any argument a project adds by hand is therefore silently
reverted by the next `gauntlet init --agent claude-code`. The same applies to
the `PostToolUse` handler, generated as
`check --gates static,size,complexity --changed --json`.

**Why it matters.** Two separate problems meet here. A project that needs to
tune the hook can only do so in the one file that regeneration overwrites, and
the reversion is silent — the retries simply come back, weeks later, with
nothing in the diff to explain them. And the `--json` default puts a
machine-readable gate report into the model's context on every file edit,
where nothing parses it; the human-readable form carries the same information
in less space, and it scales with edit count rather than with stop count, so it
is the larger consumer in a long session.

**What would address it.** Configuration that survives regeneration. A `[stop]`
table in `gauntlet.toml` read by `stop-check`, and a format option for the
fast-gate hook, would put both settings somewhere `init` does not rewrite.
Failing that, `_without_ours` could preserve arguments it did not itself
generate rather than discarding the handler entire.

**Proposed change.** Add `max_attempts` to `gauntlet.toml` and have `stop-check`
prefer it over the CLI default; default the `PostToolUse` handler to
human-readable output with `--json` opt-in; and make regeneration report what
it replaced rather than replacing silently.

**What it cost us.** Nothing realized — found by reading `scaffold.py` before
recommending the settings edit, precisely because this project's record on
reasoning about tool behaviour without reading it is bad. Had the edit been
made without that check, the reversion would have surfaced as an unexplained
regression at some later `init`.

**Routes to:** BACKLOG.md, v1. The `--json` default also belongs in whatever
covers agent-context cost, if such an item exists.

**Status.** Open.

#### Interpreter fallback lands on Gauntlet's own venv silently, and the error names the wrong thing

**What happened.** `interpreter()` resolves in order: explicit `python` in `gauntlet.toml`, the
project's local `.venv`, `$VIRTUAL_ENV`, then Gauntlet's own interpreter. When ClaimGate's `.venv`
went missing, resolution fell through to the last entry and the mutation gate reported
`No module named mutmut` from `.../uv/tools/agent-gauntlet/bin/python3`.

**Why it matters.** The message names the module; the cause was the venv. Nothing in the output says
a fallback occurred, and the path is a clue only to someone who already knows the resolution order.
The obvious reading — "mutmut got uninstalled" — sends you to fix Gauntlet's environment, and doing
so would have silenced the error while leaving every gate running against an interpreter that knows
nothing about the project's libraries. The docstring is explicit that this is exactly the situation
to avoid; the fallback that reaches it is silent.

**What would address it.** Warn when resolution lands on `sys.executable` for a project that
declares a language and has no configured `python` — that combination is almost always a missing or
broken project venv rather than an intent. Naming the fallback in the gate's error would be enough:
"no project .venv found; using Gauntlet's own interpreter, which does not carry project tooling."

**What the gap cost us.** One misdiagnosis avoided only by reading the resolution order in the
source, on a repository whose author had used the tool daily for weeks.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

#### The approval ledger is written non-atomically, and it is the one artifact no gate can rebuild

**What happened.** `registry.save` ends in `path.write_text(...)` — no temp file, no atomic
rename. A `gauntlet spec approve` or `gauntlet mutant approve` interrupted mid-write leaves
`gauntlet.lock.json` truncated. This was reached in practice: during ClaimGate item 4g a Ctrl-C
landed between two pasted approval commands, and the only reason it cost nothing is that the
interrupt fell between invocations rather than inside one.

**Why it matters.** Every other artifact Gauntlet touches can be regenerated. Specs are in git,
mutants are derived from specs, scores are recomputed on every run. The ledger is the sole record
of human judgment — approval reasons, reviewers, dates — and several of ClaimGate's run to a
paragraph of reasoning that exists nowhere else. A truncating write puts the one irreplaceable
file in the system on the least safe path.

**What would address it.** Write to a sibling temp file and `os.replace` onto the target.
`os.replace` is atomic on POSIX and on Windows, so a reader sees either the old ledger or the new
one and never a partial. Roughly three lines.

**What the gap cost us.** Nothing realized. The near miss produced a procedural workaround that
should not have to exist: commit the ledger before and after every approval run, and never invoke
an approval from a pasted multi-command block.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

**Second near miss, 2026-08-24, different mechanism.** The procedural workaround above — commit
the ledger before and after every approval run — failed silently in practice. A
`gauntlet spec approve` ran at 11:23 and its ledger write sat uncommitted in the working tree for
roughly seven hours; every gate run that day read the approval from disk (reporting the spec as
MODIFIED rather than unapproved), so nothing looked wrong, and a `git checkout -- .` at any point
would have destroyed the only record of the approval. A later session discovered it only by running
`gauntlet spec list` and noticing HEAD carried no entry at all. Beyond the atomic-write fix above,
the cheap addition this argues for: `spec approve` and `mutant approve` print a commit reminder, or
`check` warns when `gauntlet.lock.json` differs from its committed state — the ledger is the one
artifact where "uncommitted" and "at risk" are the same word.

#### An automatic retry loop repeats the one gate that rewrites the working tree

**What happened.** The stop hook retries a failing `gauntlet check`. Observed at 2, 5, and 7
attempts across ClaimGate items 4g and 4j, every time against a state that could not go green — a
drafted, unapproved spec, which is the *guaranteed* condition between a spec draft and its
approval. Instructing the agent to run the gate once does not prevent it; the loop belongs to the
harness, not the agent.

**Why it matters.** The acceptance gate mutates spec files in place and takes ~230s. Whether the
retry is harmless or dangerous depends entirely on which stage fails. An unapproved-spec failure
short-circuits at the approval check in ~0.001s before any mutation runs, so repeating it is
merely slow. A failure that reaches the mutation pass rewrites the spec once per attempt, and each
attempt is a window in which an interrupt leaves an injected mutant behind — which is how
ClaimGate's corrupted spec of 2026-08-17 was produced.

**What would address it.** Either a per-gate attempt limit, so gates that mutate the working tree
are never retried automatically; or a crash-safe mutation pass that restores from
`.gauntlet/mutation-backup/` on startup when it finds a run that never finished. The second is
strictly better, because it also covers interrupts that have nothing to do with the loop.

**What the gap cost us.** One corrupted spec, one session's diagnosis, and an initially wrong
diagnosis of *which* mutant had been injected.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

**Cost update, 2026-08-24.** The "~230s" above is stale twice over: the mutation-stage red state
was measured at 423.6s (24 mutants, item 5c pre-binding), and the green full pass at 452.7–472.8s
(48 mutants). The window this entry describes — each retry a chance for an interrupt to strand an
injected mutant — is now roughly twice as long per attempt as when it was written, and it grows
with every spec added.

#### Approval scope is coarser than the judgments it records, and it is now shaping the Gherkin

**What happened.** `gauntlet mutant approve` scopes by feature file and `--scenario`, and nothing
finer. Every survivor in a scenario shares one reason, and every re-approval overwrites all of
them. ClaimGate item 4c recorded this once: eleven survivors in one scenario, one inherited reason
that carried four inaccuracies forward invisibly, because neither the locator nor the digest moved.

**Why it matters.** It has stopped being a documentation annoyance. ClaimGate item 4g drafted an
eleven-row outline that simulated at ~31 survivors spanning three unrelated equivalence arguments —
loss-type symmetry, configuration-flag no-ops, and value substitution on unrequired fields — which
one shared reason cannot describe honestly. The specification was split into two outlines primarily
so `--scenario` could isolate them, and item 4j then pre-split its own outline for the same reason.
**The tool's scoping granularity is now determining the shape of the specifications**, which is the
wrong direction for influence to run.

**Third instance, 2026-08-23, and a different mechanism.** ClaimGate item 5b converted a plain
scenario in `features/jurisdiction_date.feature` into a two-row outline (`f6793aa`) for a reason
unrelated to approval scope: all six of the plain scenario's mutants were vacuous quoted-literal
kills, and `Examples`-column mutants are not. The conversion bought four mutants that reach the
domain where there had been none. So the Gherkin is now being shaped by two independent tool defects
rather than one — approval granularity in items 4g and 4j, mutant vacuity in 5b — and the second
distorts more, because it changes a specification's shape to buy test coverage the specification's
own content never called for.

**What would address it.** A `--locator` option accepting one or more exact locators, or a
`--column` filter within a scenario. Either lets one scenario carry several reasons.

**What the gap cost us.** One inherited reason with four inaccuracies, and three specifications
restructured to work around a tool constraint rather than because the structure was better.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

#### Mutation cannot reach a fixed Given, so a specification can state a rule nothing protects

**What happened.** `_literal_mutants` returns `[]` for any scenario where `is_outline` is true, so
in a Scenario Outline only Examples cells are mutated and a fixed `Given` above the table is never
touched regardless of quoting. `LITERAL_PATTERN` separately matches only quoted or numeric text, so
an unquoted word is invisible in a plain scenario too.

ClaimGate item 4g's first spec draft hit both at once. It stated the configuration under test — the
entire subject of the item — as unquoted fixed `Given` lines above an outline. The scenarios read as
covering both configuration states and the engine generated zero mutants against either. The file's
total rose from 116 to 122, which looked like coverage growing.

**Why it matters.** This is a gap the gate cannot report, because it has nothing to report: no
mutant, no survivor, no warning. It is distinct from the code-mutation boundary recorded below —
that one is a genuine limit of mutating code, whereas here the spec-level engine *could* mutate the
value and simply does not.

**What would address it.** Run `_literal_mutants` over an outline's steps as well, skipping only
steps containing a `<placeholder>`. A fixed `Given the loss type is "injury"` above a table is
exactly as mutable as the same line in a plain scenario, and mutating it is exactly as meaningful.

**What the gap cost us.** One spec draft round-trip, caught by an advisor reading which values the
mutants covered rather than reading the count.

**Routes to.** `BACKLOG.md`.

**Status.** Open.

### v1, blocking v2

ARCHITECTURE.md's rule is that the workspace is a client reading "the event
log and the JSON contract, and nothing else," never a private path into
internals. `.gauntlet/` artifacts are internals. These three findings are
therefore v2 preconditions rather than v1 polish: the workspace cannot route
around them by reading files directly, so the contract has to grow first.
Sequencing them as ordinary v1 work risks discovering mid-v2 that the data
the UI needs is not in the contract.

#### A gate requiring human review must show the human what to review

**What happened.** The acceptance gate refused to pass until a human judged each of 11 surviving
mutants on `features/triage.feature` equivalent or not. Its own terminal output truncated the list at
six examples plus "+5 more"; `--json` truncated the same message string identically; `gauntlet mutant
list` showed only mutants already reviewed, not the current unreviewed set. There was no CLI path to
the full eleven. Recovering it required reading the gate's own source
(`gauntlet.acceptance.mutation`) and re-deriving the mutant set by running the real algorithm against
the real feature file and the real domain code — not something a review step should require of its
reviewer.

**Why it matters.** The gate demands a judgment it will not supply the evidence for. The path of
least resistance in that position is to approve the whole block on the strength of a six-item sample
— which is exactly the failure the human-approval step exists to prevent, and in this case would have
approved a mutant (line 71) that was not equivalent and that pointed at real, previously-undocumented
behavior (see "Mutation testing can find unspecified implementation behavior" below). A gate that
requires review should make complete review possible; truncating the review material converts a
safeguard into a rubber stamp.

**What would address it.** The acceptance gate should either print the complete surviving-mutant list
(not a capped sample) or write it to a file in `.gauntlet/` the way `coverage.json` and `junit.xml`
already do, so `--json` and disk output aren't both subject to the same truncation. Until that exists,
treat a truncated mutant list as incomplete evidence, not as "the interesting ones" — the ones left
out are exactly as capable of hiding a non-equivalent mutant as the ones shown.

**Proposed change.** The acceptance gate should print the complete surviving-mutant list — not a
capped sample — or write it to a file under `.gauntlet/` the same way `coverage.json` and
`junit.xml` already are, so neither terminal output nor `--json` truncates the material a human is
required to sign off on.

**What it cost us.** The truncated six-of-eleven list nearly produced a wrong approval. The path of
least resistance — approving the whole block on the visible sample — would have signed off on a
mutant that was not actually equivalent and that concealed real, previously-undocumented behavior in
`_is_recent_inception`. Recovering the true set required reading the gate's own source code and
re-deriving the mutant algorithm by hand.

**Routes to:** BACKLOG.md, v1, blocking v2. An approval inbox physically cannot render a scenario with more than six survivors while --json truncates identically to the terminal.

**Status.** Open.

#### The approval ledger has no per-mutant reason

**What happened.** `gauntlet mutant approve` applies one `--reason` to every currently-surviving
mutant matching its filter, and a second call overwrites rather than adds. Two mutants in one
scenario surviving for genuinely different reasons cannot be recorded separately without hand-editing
`gauntlet.lock.json`, which `CLAUDE.md` forbids. The workaround is one combined reason covering both,
with each mutant's justification scoped inside the text — which works, but means a reader must parse
prose to learn why any individual mutant was approved, and a revisit trigger attached to one mutant is
not machine-associated with it.

**Why it matters.** The ledger's data model is coarser than the judgments it's asked to hold. A
reviewer relying on `gauntlet mutant list` output to answer "why is *this specific* mutant equivalent"
gets a paragraph that may address several mutants at once, with no structural marker for which
sentence belongs to which locator.

**What would address it.** A `--reason` keyed per mutant locator, or at minimum a CLI warning when a
call's survivor set spans mutants that received different reasons in the same invocation — something
short of hand-editing the lock file, which stays off-limits.

**Proposed change.** Support a `--reason` keyed per mutant locator, or at minimum have the CLI warn
when a call's survivor set spans mutants that previously received different reasons — something
short of requiring hand-editing `gauntlet.lock.json`, which stays off-limits per project policy.

**A cheaper implementation than the one proposed above.** `gauntlet review` already walks pending
items one at a time and prompts `reason (required)` per item — but `review.apply` dispatches on only
two namespaces, spec approvals and protected paths. There is no mutant branch, so acceptance
survivors are invisible to the one command in the CLI built for precisely this interaction.
Extending that walker to the mutant namespace is a smaller change than adding a per-locator
`--reason` to `mutant approve`, and it reuses a prompt that already enforces one reason per item.

**What it cost us.** First observed as awkwardness: two mutants in one scenario needing different
reasons, recorded as one combined paragraph. Later realized as an actual defect in the ledger. Ten
approvals on `duplicates.feature`'s "Matching against a single existing claim" were written in a
single call with the reason "rows already excluded by policy or loss-type mismatch; the date is
irrelevant to their outcome." That was accurate for four of them. For the other six it was false —
two sat on *matching* rows, which survive because the swapped-in date stays inside the window, and
four sat on rows excluded by loss-date distance, where policy and loss type both agree and the
recorded reason names the two dimensions that are not doing the work. All ten stayed in the ledger
under one false-for-six sentence until a reviewer checked each locator against the example table by
hand. Nothing flagged it; every digest was valid. So the combined-reason workaround does not merely
read awkwardly — here it produced a record that was wrong about most of what it covered. The coarse
call is also the path of least resistance, because the acceptance gate's own diagnostic recommends it
by name: "have a human review them with `gauntlet mutant approve`.

**Measured cost, 2026-08-14.** Item 4c's re-approval put a number on this. One reason covered eleven
survivors; by the time it was rewritten it carried four separate inaccuracies — a $500 threshold
deleted by a later item, two claims about the wider suite falsified by a different item's work, and a
threshold quoted as 30 where the scenario uses 45. All four survived two re-stampings, because
`mutant approve` applies one reason to every survivor in scope and the locator and digest never
changed. Three of the four were introduced not by carelessness but by other items invalidating claims
the reason made about files it did not own. Scoping does not help here: all eleven survivors sat in
one scenario, so `--scenario` could not isolate the five that were new.

**Routes to:** BACKLOG.md, v1, blocking v2. An inbox showing why each individual mutant was approved requires a per-locator reason to exist.

**Status.** Open.

#### Renaming a spec orphans its approval and leaves a dangling key

**What happened.** Approval keys are `spec:<path>`. Renaming `siu_flags.feature` to
`siu_indicators.feature` orphaned the approval — the new path has no key, so the spec reads as
never-approved — and left the old key pointing at a file that no longer exists. There is no
rename-aware command; the rename was a plain `git mv`. Confirmed directly: the next `gauntlet check`
reported both halves in the same run — `features/siu_flags.feature was approved but no longer
exists` and `features/siu_indicators.feature is not approved`.

**Why it matters.** Detection is not the gap — the gate names the orphaned key precisely and
supplies a remedy, and it distinguishes approved-but-missing from not-approved and
changed-since-approved as three separate states with three different remedies. The gap is that
recovery is manual: a rename costs a re-approval of the new path plus removal of the old key, with
no single operation carrying the approval across. With a handful of specs that is an annoyance; the
cost scales with spec count and rename frequency.

**What would address it.** A rename-aware approval operation that moves the key with the file.

**Proposed change.** A rename operation that moves approval keys, or at minimum a warning when a
lock key references a path that is not present.

**What it cost us.** Two manual operations per rename. Low, and in the safe direction — the gate
refuses to treat the renamed spec as approved, which is correct.

**Routes to:** BACKLOG.md, v1, blocking v2. Also the one finding here that became genuinely blocking: an approval inbox with no un-approve path inherits the same dead end. Confirmed absent from Gauntlet's README "Known issues" and BACKLOG.md — new, not a rediscovery.

**Status.** Open.

**Note on this entry.** Originally written from inference before the gate had been run, asserting
that a dangling key was "silent lock-file rot" that "nothing would have told us." The gate output
disproved both halves. Corrected after observation. Kept visible because it is the same failure
shape this document catalogues — an assertion that sounded right, written down, never checked
against what actually happens — committed inside the document that catalogues it.

**Removal has no CLI path at all, confirmed by reading the source (2026-08-09).** "Recovery is
manual" above was written before checking what "manual" actually meant. It means: hand-editing
`gauntlet.lock.json`. `gauntlet spec` has exactly two subcommands, `approve` and `list` — no
`unapprove`, `revoke`, or `prune`. The registry's `revoke()` function exists and is exercised, but
only by `mutant prune`/`prune-code`, scoped to the `mutant:` namespace; nothing wires it to `spec:`.
`gauntlet review` walks pending approvals only — a spec approved-but-missing was already approved,
so it never appears there. Confirmed empirically the same day: `features/siu_flags.feature`'s
orphaned key, left by this same reopening's rename to `siu_indicators.feature`, failed the
acceptance gate the entire time every other gate on the branch was green, and stayed that way until
a human removed it directly. On this project that direct removal is a human action full stop, not
an agent one — CLAUDE.md forbids editing `gauntlet.lock.json`, and there is no command to hand the
agent instead. The proposed change above stands; until it ships, "the rename costs a re-approval
plus removal of the old key" is more precisely "the rename costs a re-approval `gauntlet spec
approve` can do, plus a lock-file edit only the human can do."

**This entry has now been wrong twice, both times from inference rather than verification.**
First, the original text claiming a dangling key was undetectable "silent lock-file rot" — corrected
above once the gate had actually been run. Second, separately: the task that produced this
reopening's SIU indicators work asked for "the exact command" to remove the orphaned key,
presupposing one existed. It does not, as the note above establishes. Both wrong claims share the
same shape this document exists to catch: something that sounded plausible, wasn't checked against
what the tool actually does, and got acted on (or asked for) anyway. Also verified: this defect is
absent from Gauntlet's own README "Known issues" section and `BACKLOG.md`, which otherwise list real
v1 defects with workarounds — grepped directly for "dangling," "orphan," and "rename," no mention of
approval keys or spec renames anywhere in either file. This is a genuinely new finding for that
backlog, not a rediscovery of one already listed.

**Resolution, this occurrence (2026-08-09).** The human removed the four lines by hand — the key,
`approved_at`, `digest`, and closing brace. Verified independently rather than taken on report:
`git diff -- gauntlet.lock.json` showed exactly a 4-line deletion and nothing else, and `python3 -m
json.tool gauntlet.lock.json` confirmed the result parses as valid JSON. The acceptance gate's
approval check passed immediately afterward with no other change required.

### v3 — substrate

#### No cross-spec impact check

**What happened.** Making SIU indicator results three-valued invalidates `triage.feature`, whose
step definitions assert a boolean against the same shared function. This was caught by an agent
tracing the shared function across a spec boundary it had not been asked to examine.

**Why it matters.** Gauntlet would have caught it eventually — the tests gate goes red once the
change lands — but it presents as a broken test inside one spec's step definitions, not as one
spec's change invalidating another. The diagnosis points at the symptom, and it arrives after
implementation rather than at design time, when the scope decision is still cheap. With four specs a
human can hold the coupling in their head. Phase 2 adds surface, and this does not scale.

**What would address it.** Given a changed spec file, report which other spec files share step
definitions or test-API surface with it, before implementation rather than after. A warning, not a
gate — the point is to make the scope decision visible while it is still a decision.

**Proposed change.** Given a changed spec file, report which other spec files share step
definitions or test-API surface with it, before implementation rather than after. A warning, not a
gate — the point is to make the scope decision visible while it is still a decision.

**What it cost us.** Nothing this time, because it was caught by hand. The cost is the near miss:
shipping item 2 alone would have left `main` red between two reopenings, breaking the constraint the
branch discipline exists to protect.

**Routes to:** BACKLOG.md, v3. Cheap enough to land in v1 if convenient, but it only starts mattering at the scale v3's orchestration implies.

**Status.** Open.

### Convention, not code

#### Approval reasons go stale silently where the key does not

**What happened.** The `triage.feature` approval reason referenced "line 71" and "siu_flags.feature."
Both were accurate when written. A vocabulary change (`true`/`false` → `TRUE`/`FALSE`) shifted the row
to line 83, and this reopening's rename moved the file to `siu_indicators.feature`. The
content-addressed key caught the content drift and correctly reported the approval stale; nothing
caught the line number or the filename, because they live in free prose that no mechanism validates.

**Why it matters.** The reason is the entire record of why a human approved a mutant. A reason pointing
at a line that now holds something else is worse than no reason at all — a future reviewer follows it
and reads the wrong row, with no signal that anything is off, since the ledger's own freshness check
(the digest) still passes.

**What would address it / Proposed change.** None enforceable — prose cannot be validated the way a
digest can. Convention instead: approval reasons identify a case by what it is (the specific field
values, the scenario name, the mechanism), never by line number or filename, both of which drift for
reasons unrelated to whether the judgment itself still holds. Worth stating in guidance since the
ledger cannot enforce it.

**What it cost us.** Nothing this time — caught during this reopening's own mutant review, when the
current locator was checked against the live file rather than trusted from the stored reason, and the
carried-forward reason for the re-approval above was rewritten to identify the case by what it is
("the row where the mutated inception date postdates the loss date (theft / 2026-06-15)") rather than
by a line number that had already drifted once and will drift again. The near miss is the point: this
was one specific reason, checked once, by someone who happened to look.

**A second decay mode, found later, not covered by the convention above.** Identifying a case by what
it is rather than by line number does not protect a reason that asserts something about the *rest of
the suite*. The eleven-survivor `triage.feature` approval justifies itself partly by stating that the
`0 <=` lower-bound guard is undocumented — "no scenario in siu_indicators.feature, triage.feature, or
any unit test exercises an inception date later than a loss date." Item 2 added exactly that scenario
to `siu_indicators.feature` the same day. The approval is probably still valid: the mutant sits on
`triage.feature`'s row, and a scenario in another file cannot kill it. What went false is a factual
claim inside the reason, about a file the approval does not key on. Note what did *not* fire — that
approval carries a REVISIT TRIGGER, correctly scoped to the guard being removed, relaxed, or
replaced. The trigger was written for the right risk. A second, untriggered assertion in the same
prose decayed underneath it. Convention, extending the one above: a reason may state what the
approval depends on, but should not assert the state of the wider suite unless a trigger covers that
assertion too — and where it does, the claim should be dated, so a reader knows what it was true of
rather than whether it is true now.

**A second instance, and a sharper convention than the one above.** `duplicates.feature`'s ten
approvals on "Matching against a single existing claim" share one combined reason (`gauntlet.lock.json`,
approved **2026-08-11T22:51:01Z**), which explains the policy-mismatch row by quoting its value
verbatim: *"(a) Rows excluded by policy (`AU-7654321`) or by loss type (`water_damage`): the row
already yields no match on a dimension the mutation does not touch..."* `QUEUE.md` item 4a's
vocabulary-substitution reopening renames `AU-7654321` to `HO-7654321`. Only two of the ten approvals
have locator keys that embed that literal value, so only those two go stale automatically; the other
eight keep the same key, the same digest, and a reason that now names a policy number the file no
longer contains, with nothing in the ledger to flag it — a silent decay identical in shape to the
line-71/`siu_flags.feature` case above, just triggered by a rename instead of a rewrite. This is a
third decay mode, not a repeat of the two above: the reason quotes *the row's own example data*, which
is exactly what a vocabulary-substitution reopening changes by design, and the convention already
stated above — identify a case by "the specific field values" — is what *permits* this, not what
prevents it. The sharper version: **an approval reason should not quote example data values at all,
however accurately.** Describe a row by its role in the scenario — "the policy-mismatch row," "the
row excluded by loss-date distance" — never by its contents, because the contents are precisely the
part of a row a vocabulary pass is licensed to change without touching what the row proves. Both
recorded instances would have been prevented by that rule: the original entry's own
"(theft / 2026-06-15)" parenthetical, above, is itself a value-quote the sharper convention would also
disallow, and it was written to replace a *line number* — a value-quote was the fix for one fragile
reference, without noticing it was substituting one fragile reference for another. Worth stating
plainly rather than leaving implicit: this reason was authored the day after the entry above already
existed on `main` (`e2e7b89`, 2026-08-10) recording exactly this failure mode. The convention was on
record, not discovered after the fact, and got walked into anyway one reopening later.

**Routes to:** Gauntlet's contributor guidance, not BACKLOG.md. Prose cannot be validated; this is a convention for whoever writes approval reasons.

**Status.** Open, convention rather than code.

**A third instance, 2026-08-23, and one the convention above cannot reach.** ClaimGate item 5a's
survivor on "A recognized carrier's rules load with neither SIU threshold configured" mutates a
duplicate-match-window value that scenario never asserts. The value is not unprotected — a different
scenario in the same file, "A recognized carrier's rules resolve to every value the domain will
receive", both sets and asserts it. So the only honest approval reason is *"scaffolding here,
asserted there"*, and its truth condition lives in a scenario the approval does not key on. That is
the second decay mode again, reached from the opposite direction: not a stray factual claim a reason
happened to make, but the load-bearing justification itself. "Covered elsewhere" is the most common
honest equivalence reason there is, and every instance of it has this shape.

This one is not purely a convention problem, which makes it the exception to this entry's "none
enforceable". Prose cannot be validated; a *dependency* can. If an approval could name the locator
its justification rests on — structurally, beside the reason rather than inside it — the ledger could
report the approval stale when that locator's digest moves or the locator disappears, reusing the
machinery that already exists for the approval's own key. That is a much narrower promise than
validating prose, and it covers the commonest case. Worth carrying to whoever implements the
`--locator` scoping proposed under "Approval scope is coarser than the judgments it records": both
want the same addressing.

## Designed boundaries

Things the harness deliberately does not do. These are not work items — recorded so nobody mistakes
them for gaps and tries to close them.

### Gates cannot check a specification against the world

**What happened.** The 365-day reporting window, the 30-day SIU late-reporting threshold, and the
$500 theft severity threshold passed every configured gate — including 100% mutation score — for
the entire life of the project, while being, respectively: internally contradictory, orphaned
against a rule that no longer exists, and unsourced.

**Why it matters.** This is the most useful finding in this document, stated plainly: Gauntlet
verifies that code matches specification. Nothing in it verifies that the specification matches
reality. A gate can only be as correct as the human judgment that wrote the spec it's checking
against — a 100% mutation score on a wrong rule is 100% confidence in the wrong thing.

**What would address it.** Nothing about the harness — this is a designed boundary, not a defect.
It's the argument for the human review step existing at all, not a gap to close.

### Spec approval cannot verify the human read the spec

**What happened.** `gauntlet spec approve` hashes a feature file's content and records that hash as
approved. It has no way to know whether the approver read the file, read a summary of it, or
skimmed the diff.

**Why it matters.** The hash-lock mechanism guarantees the *content* hasn't silently drifted from
what was approved. It cannot and does not guarantee that approval reflected genuine review — that
guarantee, to the extent one exists, comes entirely from the human's own diligence, not from the
tool.

**What would address it.** Nothing — this is a process boundary, not a fixable gap. Worth naming
explicitly so it isn't mistaken for a guarantee the mechanism doesn't actually provide.

### Blocking a file and verifying a file are different mechanisms, and the second is not a lock

**What happened.** Gauntlet keeps two path lists in `config.py`. `DEFAULT_PROTECTED_PATHS` —
`gauntlet.toml`, `.gauntlet/`, `.claude/settings.json` and the lock file — is what the PreToolUse
guard refuses writes to. `DEFAULT_VERIFIED_PATHS` — `gauntlet.toml`, `pyproject.toml`,
`.claude/settings.json` — is what the protect gate content-hashes against the lock, failing with
`N-1/N paths unchanged` until a human re-locks. `pyproject.toml` is in the second list only. An
agent may write it; it cannot make the write stick without a human.

**Why it matters.** This is deliberate and should not be "fixed" by moving `pyproject.toml` into the
blocked list. Thresholds, gate configuration and tool scope live in that file, and an agent that
cannot draft a change to them cannot propose one — the proposal would have to be prose in a report
rather than a diff a human can read, run and lock. Blocking prevents the write; verifying routes it
through a human. Different goals, and the split between them is the design.

**What would address it.** Nothing about the boundary — it is not a gap. The one thing worth
changing is legibility. The guard's refusal message fires only for blocked paths, so an agent that
reasons about whether it may edit a *verified* path has nothing to read and gets no signal at write
time. On 2026-08-23 a ClaimGate coding agent concluded it could not edit `pyproject.toml` and
escalated an architectural decision to its human partly on that basis. Stopping and handing back was
the behaviour the project wants; one of the two constraints it cited simply did not exist. A
distinct message when a verified path is written, or a line in the guard's own documentation naming
the two lists, would have prevented it.

### Code mutation cannot find a guard no test exercises

**What happened.** The `0 <=` lower bound in `_is_recent_inception` has never been exercised with a
negative interval — every real row in every spec and unit test has an inception date on or before its
loss date. Code mutation still scores 100%, because standard mutation operators alter a comparison
(`<=` to `<`, `0` to `1`) rather than deleting a clause, and those variants are killed by the existing
inception-on-loss-date scenario. Removing the lower bound entirely is not a mutation the tool
generates, so nothing would catch it.

**Why it matters.** A 100% code mutation score does not mean every branch of a condition is defended
— only that the mutations the tool knows how to generate are caught. A guard against inputs no test
produces is invisible to it. This one was found by a mutant surviving in the spec layer, not the code
layer, which is a useful direction of travel to note: spec-level mutation surfaced a code-level gap
that code-level mutation could not.

**What would address it.** Nothing about this project's configuration — this is a property of what
mutation testing structurally can and can't generate, not a misconfiguration. Worth remembering as a
standing caveat on any 100% code-mutation score: it certifies the mutations tried, not the space of
inputs the code was never asked to handle.

**Correction, 2026-08-14.** This entry's evidence is stale. The `0 <=` lower bound in
`_is_recent_inception` *is* exercised with a negative interval, and has been since item 2 shipped on
2026-08-09: `siu_indicators.feature`'s scenario "An inception date later than the loss date does not
fire the indicator" specifies it, and `tests/unit/test_siu.py` tests it. Removing the bound would now
fail both. The general point stands — a 100% code-mutation score certifies the mutations tried, not
the space of inputs the code was never asked to handle — but the example no longer supports it.


### A same-outcome column can be the rule, not a table defect

`_discriminating_alternatives` substitutes a value drawn from the mutated cell's own column. When
the rule under specification treats every value in that column identically — by design, not by
accident — every mutation in it is equivalent and every one survives.

ClaimGate item 4g reached this deliberately: a `loss_type` column holding only `injury` and
`liability`, under a rule whose entire purpose is that the two are treated the same. Eleven rows,
eleven survivors, and no table shape fixes it. Adding discriminating rows makes it worse — measured
at 77 mutants / ~31 survivors as drafted, 84 / ~36 with a row from outside the category, and 91 /
~41 with an unrecognized row as well. The engine keeps selecting a same-category substitute, so the
extra rows add survivors in the *other* columns without touching the original eleven.

This is correct behaviour and must not be changed. The engine is reporting a true fact — the
specification does not distinguish those values because the rule does not — and a heuristic that
avoided same-outcome substitutions would suppress exactly the signal telling a reviewer that a
column is inert. The resolution belongs in the specification: remove the column, fix the value in a
`Given`, and let the symmetry be visible in the file's structure rather than recorded as equivalence
reasons in the ledger.

**Note, 2026-08-22 — what this boundary does not cover.** A run of survivors from one column is not
always this boundary, and the distinction matters because this section tells a reader what *not* to work
on. Where the rule genuinely treats the column's values alike, this entry applies and the resolution
belongs in the specification. Where the outline's expectation is not a column at all — built in the
`Then` step from a placeholder that also appears in a `Given` — the survivors are an artifact of the
engine being unable to see the expectation, and a shape change removes them; see the addition under "A
same-outcome enumeration guarantees one surviving mutant per row". The two present identically in a gate
report: one column, a run of survivors, one shared reason. Telling them apart means asking whether the
expectation is in the table. Only the second is worth restructuring for, and only the first is correct
behaviour to leave alone.

### Killed-count deltas cannot register a test that guards a cross-module invariant

**What happened.** ClaimGate item 4h added a unit test asserting that triage's high-severity loss
types are a subset of validation's recognized loss types — two frozensets in two modules, related by a
constraint stated nowhere and enforced by nothing. Predicted the code-mutation killed count would
rise. It did not: 204 killed before, 204 after, measured by isolating the gate with
`gauntlet check --gates mutation` and running it against both versions of the test file.

Two separate reasons, and both matter.

Killed count counts *killed mutants*, not killers. Remove `sinkhole` from the recognized set and the
new test does fail — alongside `validation.feature`'s row for `sinkhole`, which was already killing
that mutant. A test that only kills mutants other tests already kill moves the score by exactly zero
no matter how valuable it is.

More fundamentally, the state the test guards cannot be produced as a mutant at all. It requires a
*coordinated* edit: someone drops `sinkhole` from `RECOGNIZED_LOSS_TYPES` **and** updates
`validation.feature` to match. Validation's tests then pass, triage's severity tests pass, and only
the subset test fails. Mutation testing perturbs one thing at a time by construction, so it never
produces the inconsistent state, and no mutation operator ever will.

**Why it matters.** The natural reading of a zero delta is that the test was redundant, and a
maintainer trimming a suite on mutation evidence would delete exactly the tests that guard
cross-module consistency — the class hardest to recover once gone, because nothing else in the project
states the invariant. On ClaimGate the reasoning was recorded in `ASSUMPTIONS.md` specifically to
survive that pruning, which is a process answer to a measurement limit.

This is the second direction of the same asymmetry already recorded here. "Spec-level mutation finds
gaps code-level mutation cannot" says one layer sees what another misses. This says something
narrower and sharper: some invariants are invisible to *every* mutation layer, because they are
properties of the relationship between artifacts rather than of any one artifact.

**What would address it.** Nothing about the harness — this is a property of what single-point
mutation can generate, not a misconfiguration. Worth naming so a zero delta is not read as evidence of
redundancy. Tests guarding cross-module invariants should be judged on the coordinated edit they would
catch, which is a question for a human, not for a score.


## Properties to preserve

Things the harness does well that a refactor could break without meaning to. A
handoff document listing only complaints tells the next maintainer what to
change and nothing about what to leave alone.

### The acceptance mutation engine is importable as a plain library

**What happened.** `gauntlet.acceptance.gherkin.parse` takes a string and returns a `Feature`.
`gauntlet.acceptance.mutation.mutants` takes that `Feature` and returns `Mutant` objects carrying
locator, scenario, kind, original, mutated, and signature. Neither touches configuration, the
filesystem, the ledger, or the CLI, and neither needs a project to exist.

That made a working method possible throughout ClaimGate's phase-1 vocabulary items. Candidate specs
that were not in the repository — not committed, not written to disk, in some cases never written at
all — were measured before being proposed. Item 4e's shape decision was made this way: two candidate
outlines were built as strings, run through the engine, and compared. The same-outcome enumeration
produced thirteen guaranteed survivors; the mixed-outcome form produced thirty-two mutants and zero.
That comparison decided the spec, and it happened before a word of it was drafted, let alone locked.

The same property let every rename be checked against `git show <ref>:<path>` at both refs, so ledger
impact was known before the reopening branch was cut.

**The fidelity record, as of 2026-08-23.** Simulated survivor counts produced this way, before any
implementation existed, have matched the gate every time they were later checked against it. Item 5b
simulated zero survivors on a twenty-mutant spec; the gate found zero. Item 5a's refusal outline was
simulated at 33 mutants with "1 or 2" survivors from its blank row; the gate measured 33 and one.
That fidelity is what lets a simulation be cited as evidence rather than as a guess, and it is a
property of the engine being pure and deterministic — not of care taken by whoever ran it. A change
making mutant generation depend on the filesystem, the ledger, or an implementation being present
would end it, and the loss would not show up in any gate result.

The corollary matters as much. Item 5a's *other* survivor was never simulated, because the simulation
only modelled the blank-row question then being decided. A simulation is evidence about what it
enumerated, and silent about everything it did not. Reporting one as though it covered the file is
how a matched count becomes false confidence.

**Why it matters.** The whole discipline this document argues for — measure rather than predict,
falsify rather than confirm — rests on being able to run the engine against hypotheticals. If
`mutants()` required a config object, a project root, a `Path`, or a gate run, none of it works. The
question becomes "what did the gate report after I committed," which is a slower loop and answers a
different question, because by then the spec exists and changing it costs an approval cycle.

The cost of losing this is invisible in any test suite: everything would still pass, and the
capability would simply be gone.

**What would address it.** Nothing — this is the design working. Recorded because a plausible refactor
breaks it without touching a test: threading config through for gate-specific mutation policy, moving
locator construction into the gate, or making `parse` take a file path rather than a string. Any of
those would be reasonable-looking changes that end the ability to measure a spec that does not yet
exist.

**Routes to:** BACKLOG.md as a constraint on any acceptance-layer refactor, and Gauntlet's README
under "What building this taught us" — the engine being usable outside the gate is a feature, not an
implementation detail.

### The approval stage short-circuits before the expensive one

When a spec is unapproved or modified, the acceptance gate reports and returns in about a
millisecond, without entering the ~230s mutation pass. This is not merely an optimization. The
unapproved state is *guaranteed* on every reopening, between the spec draft and the human's
approval, so it is the failure a session hits most often and the one an automatic retry loop
repeats most. Because it fails before any file is rewritten, repeating it is safe.

Any refactor that moves approval checking after mutation, or that mutates in order to report richer
diagnostics on an unapproved spec, converts the most common failure in the workflow into the most
dangerous one.

**Figure update, 2026-08-24.** Re-confirmed on item 5c: the modified-spec state failed in 0.002s
while the same tree's full mutation pass ran 452.7–472.8s — the gap this property protects is now
five orders of magnitude wide, up from the "~230s" quoted above.

### Mutant locators are structural, not positional

A locator is scenario name, kind, column, and row values — not a line number and not a file offset.
Measured repeatedly on ClaimGate: a comment rewrite anywhere in a file, two steps added to a
`Background`, a scenario renamed elsewhere in the same file, and a whole new scenario appended each
left every existing locator and signature byte-identical, so no approval went stale. The spec digest
moved in every one of those cases and forced re-approval; not one approval needed re-review.

This is what makes editing a specification's prose affordable. If locators were positional, every
comment correction would restale the ledger, and the practical consequence would be that
specifications stop being corrected.

**Re-measured through item 5c, 2026-08-24.** Both directions again, at larger scale: adding a
column to two Scenario Outlines moved every locator in those scenarios (0 of the file's 24
pre-amendment locators survived the amendment, harmless only because none was yet approved), while
a subsequent round of comment rewrites, placeholder quoting, and a symbol removed from a comment
left all 48 locators *and* signatures byte-identical — verified by direct comparison at both refs,
twice, independently by advisor and agent.

### An approval's digest is independent of its key

**What happened.** A mutant approval key encodes *where*:
`mutant:<path>#<scenario>|<kind>|<context>`, with context being the example row's contents or the
literal step text. The entry's digest hashes `Mutant.signature`, which is `original->mutated` — the
source calls it "the mutation itself, the content whose hash an approval records." Where and what are
stored separately.

ClaimGate item 4d renamed a Scenario Outline column and three scenario titles. Six approval keys
changed; six new locators appeared. Pairing removed keys to added keys by identical digest showed each
removed key mapped to exactly one added key with the same digest — proof the six judgments were the
same six mutants at new addresses, not six mutants replaced by six others. Equal counts alone cannot
distinguish those cases, and the gate reports only counts.

**Why it matters.** Renaming is the single most common thing that moves acceptance locators, and it is
the case where a human most needs to know whether their prior judgment still applies. With the digest,
that is decidable mechanically. Without it, every rename forces a full re-review of every displaced
approval on the assumption that a moved key might be a different mutant.

The separation is easy to lose precisely because it looks redundant. The key is already
content-addressed on the whole row — see "Mutant approval keys are content-addressed on the whole
row" — so a maintainer could reasonably conclude the digest duplicates information the key already
carries. It does not. The key is sensitive to things the digest is invariant under, and that
difference is the entire signal.

**What would address it.** Nothing — recorded so the digest is not dropped as redundant. The gate does
not currently use it to classify stale approvals, which is a separate open finding, but the data being
there is what makes that fix cheap.


**Addition, 2026-08-22.** The converse holds too, and is the easier half to miss: the digest is
sensitive to things the key is invariant under. Because the substituted value is drawn from the column's
other rows, an edit anywhere in a column changes the signature of every mutant in that column while
leaving untouched rows' locators byte-identical — see the addition under "Mutant approval keys are
content-addressed on the whole row". Both directions are load-bearing. A reader who takes only the
sentence above will underestimate what a column edit disturbs, and will do so in the unsafe direction.

### An approved equivalent mutant is a regression test for its own justification

**What happened.** The line-71 approval depends on the `0 <=` lower bound in `_is_recent_inception`,
which no test exercises. That looked like a guard protected only by a reason string in a ledger. It
is not: removing the bound makes the mutant killable, the gate detects an approved mutant that no
longer survives, and the acceptance gate fails as a stale approval. The approval therefore defends
the code property that makes it valid.

**Why it matters.** This generalizes. Every equivalence approval silently asserts something about the
implementation, and the stale-approval check turns that assertion into a test. It is the strongest
answer this harness has to the question of what stops human judgments from rotting as the code moves
underneath them — stronger than the earlier prune, which only showed stale judgments being detected
after a spec changed.

**What would address it.** Nothing — this is the mechanism working as designed, worth naming so it
isn't mistaken for a coincidence. A revisit trigger written into a reason (see line 71's approval) is
belt-and-suspenders on top of a check the ledger already performs structurally.

**Correction, 2026-08-14.** The premise "which no test exercises" is stale, for the same reason
recorded under "Code mutation cannot find a guard no test exercises": `siu_indicators.feature` and
`tests/unit/test_siu.py` have both exercised that bound since 2026-08-09. The property this entry
describes is unaffected — an approval still defends the code property that makes it valid — but the
bound is now defended twice over, not only by its approval.

**Routes to:** Gauntlet's README, "What building this taught us" — it is the strongest available answer to what stops human approvals rotting as the code moves beneath them.

### Acceptance failures are diagnosed as three distinct states

The acceptance gate distinguishes approved-but-missing, not-approved, and
changed-since-approved, each with its own remedy text. This is the opposite of
the truncated mutant list, and it is what let a spec rename be diagnosed
correctly on the first run rather than presenting as a generic missing
approval. Any consolidation of acceptance diagnostics should preserve the
three-way distinction.

### Spec-level mutation finds gaps code-level mutation cannot

A surviving mutant in a feature file surfaced an undocumented guard in the
implementation that code mutation scored 100% against — see "Code mutation
cannot find a guard no test exercises" under Designed boundaries, and
"Mutation testing can find unspecified implementation behavior" below. The two
layers are not redundant. A refactor that folds spec mutation into code
mutation, or drops it as duplicative, loses the only mechanism that found that
class of defect.

## Note for the v1 effort

Two observations on `doc-updates.md`, from the side of the project being gated.

**The v1 backlog's root-cause-diagnostics item needs a fourth category.** It
currently distinguishes "tool failed," "tool found nothing," and "nothing to
measure." ClaimGate hit a fourth repeatedly: **blocked on a human decision.**
An unapproved spec is not a gate failure — no agent action clears it — and the
retry loop spent its budget against that condition three separate times, once
against a dangling approval key that had no CLI remedy at all. The category
also matters in v3: a transition query must be able to report "cannot pass
until a human acts," which is not the same as "does not pass," and a
supervisor has to handle the two differently.

**Three findings here are v2 preconditions, not v1 polish.** See the lead-in
under "v1, blocking v2" above. The short version: the workspace-as-client rule
in ARCHITECTURE.md means the workspace cannot read `.gauntlet/` artifacts to
route around truncation, a missing per-mutant reason, or a missing un-approve
path. The contract has to carry them first.

**One observation outside the plan.** Gauntlet's published README says "Ten
gates" while its own table lists eleven, and its Planned work section still
describes the boundary gate as "designed in Phase 4 and never implemented" —
while the gates table documents it and every ClaimGate run shows `boundary`
passing. The public README currently understates what has shipped.
`doc-updates.md` section 1 (delete Planned work) and section 4 (consistency
sweep) already cover this; recording it as confirmation that neither has been
applied yet.
