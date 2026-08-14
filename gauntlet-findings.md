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
what it names. When the failure is human-blocked, the expensive thing is the
run, not the bounce. A cap on the wrong quantity looks like a fix and is not
one — which is a reason to classify human-blocked states properly rather than
to keep tuning the loop around them. The narrower version, if classification is
too large a change: when the previous run in the same session failed with only
human-blocked diagnostics and nothing has changed since, re-emit that verdict
instead of running again.

**Routes to:** BACKLOG.md, v1 item 2 AND v3. See the note for the v1 effort below — this adds a fourth category to that item's taxonomy, and the same distinction recurs in v3's transition query.

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


## Properties to preserve

Things the harness does well that a refactor could break without meaning to. A
handoff document listing only complaints tells the next maintainer what to
change and nothing about what to leave alone.

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
