# Working in agent-gauntlet

This file is read at the start of every Claude Code session. `BACKLOG.md` carries the
ordered work and a memoryless status section that names the item in flight; this file
carries how to start a session, what is different about this repository, and how to close
a turn. The block headed "Quality gates (Gauntlet)" at the end is written by `gauntlet init`
and replaced whole on every re-run: it is found by the first occurrence of its begin and
end comment markers, so those two marker strings must appear nowhere else in this file.
Everything above the block is hand-written and survives `init`; edit only there.

## Session start-up

1. `git fetch origin`, then `git status --porcelain`. The working tree must be clean and the
   checked-out branch at `origin`; if either is not, stop and report what differs before
   touching anything.
2. Check the date with `date -u +%F` and `date +%F`. A session that runs past midnight
   otherwise dates its later edits with the day it began; date every edit on the day it is
   made, and say which zone.
3. Read `BACKLOG.md` "Status as of this handoff" from its last paragraph backwards until the
   item in flight is clear, then the reading table's row for that item, then everything the
   row names. Do not read `docs/session-prompts/ADVISOR.md`; it is the advisor's prompt, not
   yours.
4. `BACKLOG.md`'s stage section states the invariant the current stage holds — during
   clean-up, that the gated tree is byte-unchanged — and the command that checks it. Run
   that command now and again before every commit; it must print nothing.
5. A prompt that opens with the line `Session start-up per CLAUDE.md, then:` begins a
   fresh session on the branch and commit it names. A prompt without that line continues
   the session already running.

## Environment

- `gauntlet` on this machine is `uv tool install --editable .` over this working tree.
  Whatever this tree holds is the tool that runs here and in every hook of ClaimGate, the
  regression subject; a checkout here changes what ClaimGate's hooks run the instant it
  happens. CI runs the committed tree with `uv run gauntlet check --json`.
- The tool under change is also the checker. `stop-check` prints nothing on a pass that ran
  the gates, one line on a skip (`gauntlet stop-check skipped: gated tree unchanged since green
  run …`), and exits 1 on a crash, which Claude Code ignores, so a silent turn end proves
  nothing. A gate figure is a `gate.finished` line in `.gauntlet/events.jsonl`, quoted; never a
  memory of one. `check` and `stop-check` both emit `run.started` and `run.finished`; a
  `stop-check` that skips emits one `run.reused` line instead. The hook skips whenever your own
  `gauntlet check` was green on the same tree, so its line at a turn end is read from the log,
  never inferred. A `systemMessage` beginning "Gauntlet is blocked on a human" means stop and
  say so; the fix is the human's.
- The suite is `.venv/bin/pytest tests -q -p no:cacheprovider`. The `pytest` on PATH is not
  the venv's and collects nothing.
- The Stop hook budget is 600 s (`.claude/settings.json`) against a full own-run of under
  40 s by the event timestamps. Branch coverage has under two points of headroom over its
  floor; a change that adds an untested branch goes red here before it reaches the subject.
- ClaimGate is frozen at the annotated tag `prototype-1` (`be87d38`) and is never modified
  by this project: no spec, approval, test, source or configuration change, and no run of
  its gates except a regression run the prompt orders. A regression run costs about an
  hour and is never speculative. Its report records `git rev-parse HEAD` and an empty
  `git status --porcelain` in this repository, taken immediately before the run.
- Documents this agent edits: `BACKLOG.md`, `ARCHITECTURE.md`, `docs/GATES.md`,
  `README.md`, this file. In `gauntlet-findings.md` it edits exactly two things, from text
  the prompt gives verbatim: the `**Status.**` line of the entry being applied and that
  entry's "Change, applied" paragraph. Nothing else there, nothing in
  `docs/session-prompts/`, nothing in ClaimGate.
- Document edits are applied by a script that asserts each anchor appears exactly once,
  anchored by string never by line number, with the result pinned by sha256. A file a
  prompt names that does not exist is a stop, not a route-around, unless the prompt says
  what a missing one means.

## Save point

Every turn ends with a report the human checks against `origin`. In this order, figures
verbatim, no summaries:

1. Every judgment made beyond the prompt's text, numbered. The human rules on each before
   merge; do not resolve one silently.
2. `git log --oneline -1` for each commit made, and proof it is pushed:
   `git log --oneline origin/<branch>..<branch>` printing nothing.
3. `git diff --numstat <base>..HEAD`. For any file that is not purely additive, `sha256sum`
   of the file at HEAD; a deletion count is a property of the diff algorithm, a digest is a
   property of the file.
4. The stage invariant's command and its empty output.
5. Own-gate figures as `gate.finished` lines quoted from `.gauntlet/events.jsonl`, with the
   run id. Name every check the prompt asked for that was not run; "complete" and "not
   mentioned" must be distinguishable.
6. Stop. The human merges; the next prompt opens the next item. Do not start it because it
   is nearby.

<!-- gauntlet:begin -->
## Quality gates (Gauntlet)

This project is gated. Implementation code is yours; thresholds and approvals are
the human's.

- Run `gauntlet check` yourself before you say you are done. Do not wait for the
  Stop hook to tell you.
- Gate failures come back as JSON with a file, a symbol, a line, and a remedy.
  Act on the remedy rather than guessing.
- Never edit `gauntlet.toml`, `gauntlet.lock.json`, `.claude/settings.json`, or
  anything under `.gauntlet/`. Weakening a threshold is not a way to pass a gate.
  If you believe a threshold is genuinely wrong, say so and let the human decide.
- Write tests that would fail if the behavior were wrong. Coverage of code that
  asserts nothing is worthless and later gates are designed to catch it.
- Prefer extracting functions over suppressing a finding. `# noqa` and
  `# type: ignore` are last resorts, not shortcuts.
<!-- gauntlet:end -->
