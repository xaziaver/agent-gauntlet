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
    comparison names two tags. *(Tagged and pushed 2026-09-13; the tag is annotated.)*

G2. **Document consolidation.** Six parts, in order.

G2a. *(Closed 2026-09-12 — `d49f259`.)* `doc-updates.md`, the August 2026 documentation plan the
    findings cite three times, committed as found (sha256 `66d587cd4f34357d`). Sections 1, 2 and 4
    are applied in G2d; section 3 is superseded by the v1 order.

G2b. *(Closed 2026-09-12 — `a8b9034`.)* `docs/session-prompts/ADVISOR.md`, the advisor start-up
    prompt (sha256 `2b7ae3793e0aea70`). Not in the coding agent's reading list.

G2c. *(Closed 2026-09-12 — `751382c`.)* This file becomes the live queue:
    the clean-up stage, a reading table, a memoryless status section, and a dated note under each of
    the seven August items. Produced by a tested script with every anchor asserted unique and the
    result pinned by sha256.

G2d. *(Closed 2026-09-13 — `d12e348`.)* `README.md` and
    `ARCHITECTURE.md` per `doc-updates.md` sections 1, 2 and 4, with two departures
    from section 1: "Planned work" and "Known issues" are kept and annotated in place — shipped, with
    the symbol, or open — because the findings cite both by name; and the "one small project" claim
    in "Planned work" is annotated, not deleted. After the roadmap replacement the C# adapter is named
    once, which is what section 4 asks.

G2e. *(Closed 2026-09-13 — `2fdc06d`.)* `CLAUDE.md` gains "Session
    start-up", "Environment" and "Save point" sections above the scaffold block; the text between
    the markers stays byte-identical to what `scaffold.upsert_block` emits. The sections sit above
    the block because that is the side `tests/test_scaffold.py` pins, and the prose does not spell
    the marker strings because `upsert_block` finds the block by their first occurrence
    (advisor-measured 2026-09-13).

G2f. *(This commit; closes G2.)* `.gitignore` audited, last and alone: line 14, `.\#*mutants/`,
    split into the Emacs lock-file rule it was meant to be, the duplicate `.mutmut-cache` on line 15
    removed, every rule annotated with what it hides. Checked by `git check-ignore -v .#x.py` naming
    a rule after and none before, and by eighteen probe paths whose outcomes are otherwise unchanged.

G3. **The harness moves against the frozen tag**, in the note's order, one entry per commit. Each
    entry gains a "Predicted effect on the regression subject" paragraph, ratified by the human,
    before its code moves. None of the eight entries the note orders has one yet (inventoried
    2026-09-12); the only such paragraph in the file is under "The Stop hook runs every gate after
    the first failure", the one entry already applied, and it is the model.

G4. **ClaimGate phase 4 opens on the harness G3 produces.** Not this repository's work.

## G3 stage

The harness moves against the frozen tag, in the note's order, one findings entry per item, each on
its own `v1/item-<n>-<name>` branch. What stays fixed: this repository's own protected paths and its
build metadata — `git diff --name-only a0ef78d HEAD -- gauntlet.toml gauntlet.lock.json
pyproject.toml .claude` prints nothing after every commit — and ClaimGate, which is never edited,
approved, or run except for the one regression run per item. Per item: the entry's "Predicted
effect on the regression subject" paragraph is ratified before code moves; the tool's own nine gates
are green at every turn end; the regression run is `gauntlet check` in a clean clone of `be87d38`
with this repository's commit and an empty `git status --porcelain` recorded immediately before it;
and the verdict is compared line by line with the prediction. A difference the prediction did not
name is a stop, not a correction. Item 1 additionally leaves `src/gauntlet/acceptance/mutation.py`,
`src/gauntlet/acceptance/gherkin.py`, `src/gauntlet/mutants.py` and `src/gauntlet/registry.py`
untouched, so the engine's enumeration at the tag (1263 = 808 `example` + 455 `literal`) cannot move.

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
| G3 item 1 | the entry "The acceptance gate runs the entire steps directory once per mutant, so wall time is scenarios × mutants" in full — its design-decisions and prediction paragraphs are the brief; then "The acceptance gate re-runs every mutant on every check", its "Constraint on any fix here" paragraph twice; *Properties to preserve* "An approved equivalent mutant is a regression test for its own justification"; `src/gauntlet/gates/acceptance.py` `survivors_for` and `_survivors`; `src/gauntlet/adapters/python.py` `run_acceptance`; `src/gauntlet/mutants.py` `classify`; `gauntlet.toml` `[project]` and `[gates.acceptance]`; `docs/GATES.md` "acceptance" |
| G3 item 2 | the entry "The stop-check records no tree hash, so a documents-only turn pays a full run" in full, including its 2026-09-11 paragraphs — the property paragraph is a constraint, not advice; "Run pairing in the event log is unreliable in two directions" and its ready patch; "The acceptance gate re-runs every mutant on every check" with its 2026-09-13 and 2026-09-14 annotations (its cache remedy folds in here); "The Stop hook cannot be scoped, and the prescribed workflow produces a phase where it cannot pass" with its 2026-09-06 correction; `src/gauntlet/cli.py` `check`, `stop_check` and `_finish`; `src/gauntlet/runner.py` `run_full_gauntlet` and `build_context`; `src/gauntlet/events.py`; `src/gauntlet/config.py` (which paths Gauntlet knows as gated); ClaimGate's `.claude/hooks/stop-check.sh` and `.claude/settings.json` at `be87d38`, read-only, for the hash the wrapper computes and what calls it |
| G3 item 3 | the entry "The only record of a verdict is a local log that is ignored by git and rotates destructively" in full, with its 2026-09-12 and 2026-09-13 annotations — the harness fields are a constraint; "The stop-check records no tree hash" Design decisions (4) and (5) and its Change-applied paragraph (what `.gauntlet/last-green.json` is and is not); *Properties to preserve* "A stop-check on an unchanged wholly green tree skips in seconds, and every failure to hash is a full run"; `src/gauntlet/events.py`; `src/gauntlet/cli.py` `check`, `_finish` and the `--json` report path; `src/gauntlet/tree.py` `Invocation`, `remember`, `wholly_green`; `gauntlet.toml` `[output]` and `[protect]`; ClaimGate's `docs/queue-history/events-prototype-1.jsonl` on its `main`, read-only, as the archived baseline the record must be able to stand in for |
| G3 item 4 | the entry "Run pairing in the event log is unreliable in two directions" in full — its ready patch, re-anchored by string, and its 2026-09-15 annotation are the brief; "The stop-check records no tree hash" decision (6) and its Change-applied paragraph (the stop-check half, already applied); `src/gauntlet/cli.py` `check`, `_stop_gates`, `_locked_run` and `_finish`; `src/gauntlet/status.py` and `cli_events.py` for every reader of `run.started`; `tests/test_cli.py` `test_a_concurrent_run_exits_zero_rather_than_interleaving` |
| G3 item 5 | the entry "Interrupted mutation runs leave corrupted source" in full — its events, the 2026-09-14 annotation, and the design decisions and prediction paragraphs once they exist are the brief; "An automatic retry loop repeats the one gate that rewrites the working tree" for the backup-diff-plus-digest argument; `src/gauntlet/gates/acceptance.py` `_backup` and `_survivors`; `src/gauntlet/adapters/python.py` `run_acceptance`; ClaimGate's `.claude/hooks/stop-check.sh` and `.claude/settings.json` at `be87d38`, read-only, for how the hook is bounded and killed; `tests/test_acceptance_gate.py::test_mutation_restores_the_feature_file` |
| G3 item 6 | the three entries the note names — "The acceptance gate short-circuits mutation on an approval failure", "The Stop hook cannot be scoped, and the prescribed workflow produces a phase where it cannot pass", "Retry loop burns attempts on non-agent-actionable failures" — in full with their annotations, and the design decisions and prediction paragraphs once they exist; `src/gauntlet/gates/acceptance.py` `_stages` and the three stage functions; `src/gauntlet/cli.py` `stop_check` and `_stop_gates`; `src/gauntlet/loop.py`; ClaimGate's `.claude/settings.json` and `.claude/hooks/stop-check.sh` at `be87d38`, read-only |
| G3 item 7 | `gauntlet-findings.md` "Note for the v1 effort" item 7 and its 2026-09-17 annotation — the tail of v1, one prediction per change rather than one design per session; the near-miss entries, ledger atomicity first ("The approval ledger is written non-atomically, and it is the one artifact no gate can rebuild", then "`run_cmd` decodes tool output strictly, so a non-UTF-8 byte from any tool is an uncaught exception in a hook"); then every entry under "Proposed changes to Gauntlet" whose `**Status.**` line does not begin "Applied" or "Resolved", in file order, with the entries this effort deferred rather than fixed among them; the Change-applied paragraphs of items 3 to 6 for the debts they banked |
| G3, any entry | `gauntlet-findings.md` "Note for the v1 effort", then the entry in full; `ARCHITECTURE.md` "Contracts you must not break" and "Conventions"; `docs/GATES.md` for the gate touched |

## Status as of this handoff

**2026-09-20, G3 item 7 change 3 applied (`gauntlet mutant preview`).** On
`v1/item-7-change-3-mutant-preview` from `328ff5f`, no open commit: the human findings commit
`b55a32d` (design decisions (1)-(6): the exit status follows the file, it reads the file and nothing
else, one file in with `diff` as the two-input form, `locator<TAB>signature` with the count by kind
on stderr, the Background blind spot in the help, no `survivors_for`; and the second-shape reason
corrected — `cli.py` imports every `cli_*` module at load and Typer builds every subcommand before
it dispatches to one, so a command's declaration is on every invocation's path, the Stop hook's
included, and only its body is outside the subject's run), `87f7877` (the command and nine tests,
614 → 623, `cli_mutants.py` 151 → 191 of 300), `e9be636` (README, `docs/GATES.md`,
`ARCHITECTURE.md`), `99ba679` (one assertion strengthened, shown to fail first). Verified against
`origin` by the advisor at every step. Second shape, so no regression run: own gates nine green at
each commit — run `20260920T143457-139464` at the tip, 623/623, 97.07 / 93.11, tree `21144da3…` over
98, agent-quoted — and the entry's measured row re-run by the advisor from a clone: 1263 lines over
the tag's sixteen specs, 808 `example` and 455 `literal`, equal to the engine's enumeration. The
harness moved, `43407aa4e7458e98…` → `5fa4fb351e88f318…` over 53: the next verdict-path change's
regression session recomputes it and quotes nobody's. Item 7 stands at three of the ground report's
33 v1 entries applied; the entries of changes 1 and 2 still read `**Status.** Open.` and are
corrected at the next save point. Merge to `main` is the human's next act; change 4 opens with the
advisor pricing the next open entry in file order.

**2026-09-20, G3 item 7 change 2 applied (`run_cmd` fails closed on undecodable output).** On
`v1/item-7-change-2-run-cmd-decoding` from `28caa08`, no open commit — the reading table already
carries item 7's row: the human findings commit `95a6dd2` (design decisions (1)-(4): fail closed
rather than `errors="replace"`, keep `text=True`, `UNDECODABLE_RETURNCODE = 120` outside the shell's
reserved codes, item 2's now-unreachable narrow fix in `tree._listing` comes out; the extraction,
the prediction, the matrix and four test names), `ed747dd` (extraction: `_failed` in
`gates/base.py`, `run_cmd` 24 → 20), `b5aa430` (the change and its tests, 611 → 614, one mock-only
test replaced by one against a real undecodable file name). Verified against `origin` by the
advisor at every step. Two proofs: the matrix, each arm's `tree` bound to its own `base`, every row
as predicted, R5 returning None on both arms through different branches; and regression run
`20260920T112316-111530` in the item-1 clone at `be87d38` with Gauntlet at `b5aa430`, harness equal
to the tip's, eleven tuples identical to the tag's, `run.finished` `a8a00163…` over 127, lock
`61c2ac4d30025e8c`, record digest `9c7aececf56dc4f5…`, skip `20260920T113821-128891`, acceptance
863.854 s. Debt: `run_cmd` at 25 of 25 beside `_column_mutants`. Merge to `main` is the human's next
act; change 3 opens on its own branch.

**2026-09-19, G3 item 7 change 1 applied (ledger atomicity).** On
`v1/item-7-tail` from `414f899`: `8d0f2c0` (open: the reading-table row and item 6's status
sentence), the human findings commit `aff05b4` (design decisions (1)-(3), the predicted effect on
the subject, the second-proof matrix and three test names), `3891136` (the change and its three
tests), `18a15b9` (the amendment: decisions (1) and (3) reversed, after the duplication gate went
red on the specified shape at threshold 0 and after the premise that `registry.py` cannot import a
Gauntlet module was measured false — `gates/` has no `__init__.py`, `gates/base.py` imports none,
and eleven modules outside `gates/` already import it), `cef5b6f` (decision (4): `save` hands its
text to `write_text_atomic`). Verified against `origin` by the advisor at every step. Two proofs:
the matrix, run at both implementations with its nine result lines byte-identical; and regression
run `20260919T095612-48662` in the item-1 clone at `be87d38` with Gauntlet at `cef5b6f`, harness
equal to the tip's, eleven tuples identical to the tag's, `run.finished` `a8a00163…` over 127, lock
`61c2ac4d30025e8c`, record digest `9c7aececf56dc4f5…`, skip `20260919T101114-65625`, acceptance
847.984 s against the tag's 3736.757 s. `.gauntlet/` holds seven entries after a `check` and eight
after a skip, since item 6's `d9e835d`; the seven-entry listing recorded at item 6's close was the
post-check one. Item 7 is a sequence and not one change: from here it runs one branch per change,
each merged on its own proof. Merge to `main` is the human's next act.

**2026-09-17, G3 item 6 applied.** On `v1/item-6-approval-and-hook` from `a3d4605`: `cf54898`
(open), the human findings commit `ab5d6d9` (design decisions (1)-(5) across the three entries and
two predictions), `5b6688d` (extraction: `init` and `guard` to `cli_setup.py`, `cli.py` 288 → 226),
`d9e835d` (the change: "; mutation not run" on the acceptance gate's early returns;
`stop.human_blocked` — approval findings only — with `stop-check` escalating a human-blocked run at
once without an attempt and `gauntlet loop` stopping after one; `reason` on `agent.escalated`;
eleven tests and one vacuous assertion fixed). "The Stop hook cannot be scoped" resolved by
measurement, no code. Verified against `origin` by the advisor at every step. Two proofs: the ground
report's throwaways, every row as predicted; and regression run `20260917T212700-8978`, `check
--record` in the item-1 clone at `be87d38` with Gauntlet at `d9e835d`: exit 0 in 880 s, eleven
tuples identical to the tag's (agent and advisor), log identical to item 5's with ids, times and
durations stripped, `run.finished` `a8a00163…` over 127, lock `61c2ac4d30025e8c`, record digest
`9c7aececf56dc4f5…`. Skip `20260917T214205-26154`, 0.147 s. Merged to `main` at `4b76ca4`; item 7 opens on `v1/item-7-tail`.
Own baseline updated below. Debts: `acceptance.py` at 291 of 300; `check` and `stop_check` at 24 of
25; `drive` at 24; `verdict compare` deferred; the acceptance path defaults still restated in
`tree.py`; a dangling `spec:` key has no CLI remedy ("Renaming a spec orphans its approval").

**2026-09-16, G3 item 5 applied.** On `v1/item-5-restore-on-interrupt` from `65ddae3`: `fa28bc4`
(open), the human findings commit `74d31df` (design decisions (1)-(6) and two predictions,
subject and kill matrix, ratified before code moved), `1b4302a` (extraction: `acceptance/strands.py`),
`b460b99` (the change: `signals_raise` and `Interrupted.die()` in `gates/base.py`, atomic spec
writes, backups mirrored and discarded after restore, `restore_all` at the gate's start with the
count in `actual`, `run.interrupted` in the log; thirteen tests, one a real SIGTERM kill). Verified
against `origin` by the advisor at every step. Two proofs: the kill matrix in the rebuilt
throwaways — SIGINT, SIGTERM, SIGHUP and `timeout` restore and log the signal, SIGKILL strands and
the next run repairs it and says so — and regression run `20260916T223154-47209`, `check --record`
in the item-1 clone at `be87d38` with Gauntlet at `b460b99`: exit 0 in 1092 s, eleven tuples
identical to the tag's (agent and advisor), log identical to item 4's with ids, times and
durations stripped, `run.finished` `a8a00163…` over 127, lock `61c2ac4d30025e8c`, record digest
`9c7aececf56dc4f5…`, and `.gauntlet/` without `mutation-backup` after, the one named difference.
Skip `20260916T225018-64532`, 0.16 s. Merged to `main`; item 6 opens on
`v1/item-6-approval-and-hook`. Own baseline updated below. Debts: `acceptance.py` at 289 of 300; `check` at 24 of 25;
`verdict compare` deferred; the acceptance path defaults still restated in `tree.py`.

**2026-09-15, G3 item 4 applied (the `check` half).** On `v1/item-4-run-started-in-lock` from
`a0386af`: `a92eb13` (open), `ecec591` (housekeeping outside the verdict path: `deferred_to([])`,
`ShortGateLineError`), the human findings commit `6d64fba` (design decisions (1)-(6) and a "nothing
changes" prediction, ratified before code moved), `8f0b8bf` (housekeeping: `export` refuses a run
with no `gate.finished` line), `ca9d42d` (the change: `check`'s `run.started` emit inside the lock,
`cli.py` 284 → 288, `check` 24 of 25, one test, ARCHITECTURE.md and GATES.md amended), `2eed979`
(`AcceptanceAdapter` deleted, its entry closed). Verified against `origin` by the advisor at every
step: footprints, digests, sizes by `ast`, both pipelines from a clean clone. Regression run
`20260915T124953-2826892`, `check --record` in the item-1 clone at `be87d38` with Gauntlet at
`2eed979` in the venv: exit 0 in 995 s, eleven tuples identical to the tag's, compared by the agent
and by the advisor; the log identical to item 3's with ids, times and durations stripped,
`run.started` still first; `run.finished` `a8a00163…` over 127; lock `61c2ac4d30025e8c`; record
digest `9c7aececf56dc4f5…`. Skip `20260915T130701-2844199`, 0.207 s. Export of the tag's run
byte-equal to item 3's. Nothing outside the prediction appeared. Merged to `main`; item 5 opens on
`v1/item-5-restore-on-interrupt`. Own baseline updated below. Debts: `check` at 24 of 25, next change to
it extracts first; `verdict compare` still deferred; the acceptance path defaults still restated in
`tree.py`.

**2026-09-15, G3 item 3 applied.** `c42426c` (extraction: `doctor` and `version` to `cli_doctor.py`,
`cli.py` 295 → 274) and `81b2bcb` (the change) on `v1/item-3-committed-verdict`, on top of the human
findings commit `aac3869` and the opening `85125ee`; design decisions (1)-(9) and the prediction
ratified 2026-09-15 before any code moved; verified against `origin` by the advisor: footprint,
digests, sizes by `ast`, the own gated tree `e3e172a8…` over 95 and the harness digest `a0e9b46e…`
over 51 recomputed by the shell pipelines from a clean clone, both records read field by field
against the logs. Regression run `20260915T102408-2800787`, `gauntlet check --record
~/gauntlet-review/item3-verdict.json` in the item-1 clone at `be87d38` with `.gauntlet/` and
`mutants/` removed, Gauntlet at `81b2bcb` installed into the clone's venv (`uv pip install
--reinstall-package agent-gauntlet --python .venv/bin/python`) and `verdict.harness()` printing the
tip's pipeline values before the run: exit 0 in 996 s; all eleven `gate.finished` tuples identical
to the tag's, compared by the agent and again by the advisor from the archived log; `run.finished`
`a8a00163…` over 127; lock `61c2ac4d30025e8c` and clone tree unchanged after; the record's
`verdict_sha256` `9c7aececf56dc4f5…`, the value predicted from the archive. Then the skip, run
`20260915T104103-2818371`, 0.147 s, one `run.reused`. Then `verdict export` of the tag's run from a
copy of the archive: the same digest, seven null fields, the archive unchanged; the tag's record is
`~/gauntlet-review/prototype-1-verdict.json`, to be committed to ClaimGate in C4. Acceptance 966.337
s, under item 2's 1,014.333 s, which the prediction wrongly called a floor; durations are outside
the proof. Merged to `main`; item 4, reduced to its `check` half, opens on `v1/item-4-run-started-in-lock`. Own baseline updated below. Debts banked in the entry: `verdict.deferred_to([])` and
`from_lines` on a line missing a key both raise; `verdict compare` deferred; the acceptance path
defaults still restated in `tree.py`.

**2026-09-14, G3 item 2 applied.** `1faa85e` and `8b64ca0` on `v1/item-2-tree-hash-skip`, on
top of the human findings commit `73beee5` and the opening `c3e5b40`; design decisions (1)-(8)
and the prediction ratified before any code moved; verified against `origin` by the advisor:
footprint, digests, the own-tree hash recomputed by the shell pipeline at both commits, tree.py
read in full. Regression run `20260914T171042-2731382`, `gauntlet check` in the item-1 clone at
`be87d38` with `.gauntlet/` and `mutants/` removed first (a clone whose `.gauntlet/` is removed
counts as fresh for everything the tool reads), Gauntlet at `8b64ca0` installed into the
clone's uv venv (`uv pip install --python .venv/bin/python`; the venv has no pip, and item 1 had
run the uv tool on PATH), `gauntlet doctor` clean, this repository's porcelain empty: exit 0 in
17 m 35 s; all eleven `gate.finished` tuples identical to `20260913T222906-2657107` and so to
the tag's, compared by the agent and again by the advisor from the archived log; `run.finished`
carrying tree `a8a00163534b8737…` over 127 files, the value predicted from a clean archive of
the tag; lock `61c2ac4d30025e8c` unchanged; clone tree clean after. Then
`printf '{}' | gauntlet stop-check --max-attempts 1` on the unchanged tree, run
`20260914T172831-2750689`: 0.198 s, exit 0, one `run.reused` line, nothing else. Acceptance
1,014.333 s; static 3.821 s and mutation 26.274 s, both cold. Own baseline updated below.
Merged to `main`; item 3 opens on `v1/item-3-committed-verdict`. Item 4 is reduced to its
`check` half. Debts banked in the entry: acceptance path defaults restated in `tree.py`;
`cli.py` at 296 of 300 (295 by the size gate's rule, as item 3 found).

**2026-09-14, G3 item 1 applied.** `ae591d5` and `3ef2745` on `v1/item-1-per-mutant-scoping`, on
top of the human findings commits `675dd9f` and `e8b5370` and the housekeeping `0f2a5ff`;
verified against `origin` by the advisor: footprint, digests, every transcribed passage, sizes
from `ast`, twelve tests plus one. Regression run `20260913T222906-2657107`, `gauntlet check` in a
fresh clone of `be87d38` (`~/gauntlet-review/claimgate-item1`, toolchain from
`requirements-dev.txt`, `gauntlet doctor` clean) with this repository at `3ef2745` and porcelain
empty recorded before it: exit 0; all eleven `gate.finished` tuples identical to
`20260911T110451-2238600`, compared by the agent and again by the advisor from the archived log;
lock `61c2ac4d30025e8c` unchanged; clone tree clean after; `.gauntlet/acceptance-scope.json` names
one module per feature, `scope: module`. Acceptance 1,042.331 s against the baseline's 3,736.757 s
— the figure every later G3 run should expect from that gate. A first launch,
`20260913T222806-2655353`, was stopped seventeen seconds in during the mutation gate; its leftover
`mutants/` was removed and that gate re-run alone (run `20260914T105020-2707417`: score 100.0 %, 757 killed).
Own baseline updated below. Merged to `main` at `2e4970d` (`--no-ff`, human; the merge subject
carries a literal `<COMMIT_4>` from an advisor-written command, left as is). Item 2 opened on `v1/item-2-tree-hash-skip` at `c3e5b40`; see the paragraph above.

**2026-09-13, close of clean-up.** G2f landed at `1539205`, verified against `origin` by the advisor;
`0449c6b`, `2fdc06d` and `1539205` were merged to `main` at `c6c22da`, one `--no-ff` merge with
`cleanup/documents` fast-forwarded to it. The 2026-09-13 advisor session's findings save point is
`a543e89`, a human commit that also corrects three passages of `docs/session-prompts/ADVISOR.md`;
`main` was fast-forwarded to it. The Stop hook's own runs after G2e (`20260913T102023-2604660`) and
G2f (`20260913T104021-2606400`) were read by the human from the event lines: nine gates green each,
actuals identical to the baseline below. The clean-up stage is closed and `cleanup/documents` is
finished. G3 opens on `v1/item-1-per-mutant-scoping`. This commit is housekeeping only, paired with
a read-only report on item 1's ground — its anchors located by string at this ref, module and
function sizes against the size gate's ceilings, the tests that exercise them — written to the
owner's review directory for the next advisor session, which drafts item 1's "Predicted effect on
the regression subject" paragraph and has it ratified before any code moves. The gated tree is
unchanged since `a0ef78d`.

**The regression subject.** ClaimGate at the annotated tag `prototype-1`, commit `be87d38`. Its
`gauntlet.lock.json` is sha256 `61c2ac4d30025e8c`, 92 entries: 16 spec, 73 mutant, 3 config. The
engine at `a0ef78d` enumerates 1263 acceptance mutants over the sixteen specs, 808 of kind `example`
and 455 of kind `literal` (advisor-measured 2026-09-12 from `git archive prototype-1`). The sixteen
locked spec digests are listed in ClaimGate's `QUEUE.md` status section. The verdict every G3 change
is compared against is run `20260911T110451-2238600`, the tag's last stop-check, archived on
ClaimGate's `main` at `docs/queue-history/events-prototype-1.jsonl` — first committed at `de2c23a`,
after the tag, so `git archive prototype-1` does not contain it — (3912 lines, 836,642 bytes, sha256
`49395ea8c36d633f`): eleven `gate.finished` lines, all `passed: true`, `diagnostics: 0`, `error:
null` — protect 3/3 paths unchanged; static 0 findings; size worst function 25; complexity 6;
boundary 18 step file(s), 0 direct import(s); tests 966/966 passing; coverage line 100.0, branch
100.0; crap 6.0; duplication 0; mutation score 100.0 %, 757 killed; acceptance 16 spec(s), 73
reviewed-equivalent, 3736.757 s against ClaimGate's 7200 s Stop budget. An identical verdict means
those eleven tuples of `gate`, `passed`, `error`, `diagnostics` and `actual` unchanged, the lock
byte-identical, the subject's working tree clean after the run, and no other event-log difference
the entry's prediction did not name. A regression run is `gauntlet check --record <a path outside
the clone>` in a clean clone of the tag (since item 3; about seventeen minutes since item 1), with
this repository's commit and an empty `git status --porcelain` here recorded immediately before it,
and the record's `harness.source` equal to `cd src/gauntlet && git ls-files -z | LC_ALL=C sort -z |
xargs -0 sha256sum | sha256sum` at that commit: `gauntlet` is installed with `uv tool install
--editable .`, so this working tree is the tool, and a checkout here changes what every ClaimGate hook runs at once.

**This repository's own baseline.** Nine gates configured: protect, static, size, complexity, tests,
coverage, crap, duplication, acceptance; no `[gates.boundary]` or `[gates.mutation]`.
The `gauntlet check --record` after item 7 change 2, run `20260920T105337-110010`, stamped
2026-09-20T10:53:37Z to 10:54:28Z, agent-quoted and read by the advisor from the paste: protect 3/3
paths unchanged; static 0 findings; size worst function 25; complexity 6; tests 614/614 passing in
50.306 s; coverage line 97.05, branch 93.07 against floors of 95, 90 and per-file 80; crap 9.32;
duplication 0; acceptance "no feature files" (vacuous). Diagnostics 0 and error null on all nine;
`run.finished` tree `74f3b323859a5e60…` over 98 files; the harness `43407aa4e7458e98…` over 53,
recomputed by the advisor by the shell pipeline from a clean clone at `899615e`. Before item 7
(run `20260917T094153-80919`) the suite was 608 tests in 47.619 s at 97.04 / 93.07 over 98 files,
harness `e0672d331c6c74c8…`. Before item 6 (run `20260916T221205-8596`) the suite was 589 tests in 57.216 s
at 96.9 / 92.68 over 97 files.
Before item 5 (run `20260915T121906-2825022`) the suite was 576 tests in
58.108 s at 96.89 / 92.5 over 95 files.
Before item 4 (run `20260915T101125-2799622`) the suite was 572 tests in 51.356
s at 96.87 / 92.41 over 95 files. Before item 3 (run
`20260914T161254-2726665`) the suite was 551 tests in 49.7 s at 96.76 / 92.23 over 90 files. Before
item 2 (run `20260913T222626-2654730`) the suite was 511 tests in 50.161 s at 96.6 / 91.89. Before item 1 (run
`20260913T093143-2601684`, after G2d) the suite was 498 tests in 36.328 s at 96.54 / 91.75; the two
item-1 tests that run a real pytest-bdd project account for about 9 s of the difference. Stop hook
budget 600 s; a full own-run is about 51 s by the timestamps. The suite is `.venv/bin/pytest tests
-q -p no:cacheprovider`; the `pytest` on PATH is not the venv's and collects nothing. Branch
coverage has 3.07 points of headroom over its floor: a G3 change that adds an untested branch goes
red here before it reaches the subject. Since item 2 the Stop hook skips whenever the hand `gauntlet check` was green on the same
tree: a turn end that ran no gate is a `run.reused` line in the log naming that run, and only
the log tells it from a crash.
`cli.py` is at 248 of 300 lines since item 6 moved `init` and `guard` to `cli_setup.py`, with
`check` and `stop_check` at 24 of 25; `gates/acceptance.py` is 291 with `_survivors` at 22;
`loop.py` 151 with `drive` at 24; `gates/base.py` 214 with `run_cmd` at 25 of 25 since item 7
change 2; `acceptance/mutation.py` 247 with `_column_mutants` at 25 of 25; `registry.py` 241 since
change 1 and `tree.py` 249 since change 2; `stop.py` 95, `acceptance/strands.py` 71, `runner.py`
144, `verdict.py` 210, `cli_verdict.py` 54. The two functions at the ceiling each force an
extraction before the next change to them.

**The inventory of 2026-09-12**, read-only, agent-produced, from which this file was written.
Three source-line citations in the findings resolve at `a0ef78d` (`cli.py:151` and `cli.py:151-152`
exactly; `cli.py:235` has drifted to 232). "v1 item 2 (root-cause diagnostics)" at findings lines
863 and 1011 means `doc-updates.md` section 3's item 2, which was never applied here; item 2 of this
file is mutation cost. `.claude/settings.json` is byte-identical to the scaffold's output, and
`CLAUDE.md` was until G2e; its marked block still is. All three lock digests match. CI runs
`uv run gauntlet check --json` on push to `main`, on
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
