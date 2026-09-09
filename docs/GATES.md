# How the gates work

A companion to `README.md` ("The gates in detail") and `ARCHITECTURE.md`. The README says what
each gate is for in a paragraph; `ARCHITECTURE.md` says what contracts a gate must honour. This
document is the layer between: for each gate, why it exists, what it actually runs, what it reads, how it
decides, what its configuration keys are, and the technical decisions inside it that are easy to
misread from the source. Everything here was written from the code at `4fc5c34`, not from memory.

Paths are relative to `src/gauntlet/`. Every gate lives in `gates/<name>.py` and exposes
`name` and `run(ctx, config) -> GateResult`.

## Why gates at all

An AI coding agent is fast, tireless, and unreliable in one specific way: it produces work
that *looks* finished. It writes a function and reports that the tests pass; it writes tests that
assert nothing; it duplicates a helper it could not find; it loosens a threshold to get green. None
of this is malice — it is what optimizing for "the task appears done" produces.

A gate is a check that runs automatically after every piece of work, that the agent cannot edit,
and that turns "appears done" into "measurably done." The human's job shrinks to two things:
setting the thresholds, and approving what only a human can judge. Everything else the machine
enforces.

The eleven gates run in a fixed order, cheapest first, so a syntax error is reported in a second
rather than after a long run. Each section below says what the gate is for first, then how it is implemented.

## The shape shared by every gate

Read `gates/base.py` first; the rest is variations on it.

**`GateContext`** is everything a gate may look at: `project_root`, `src`, `tests`, the list of
`changed_files` (or `None`, meaning a full run), the enabled gate names, the paths the protect
gate verifies, and the interpreter to hand to subprocesses. Two helpers matter:

- `python_files()` — the analyzable `.py` files under `src/`, narrowed to `changed_files` under
  `--changed`. "Analyzable" excludes Emacs lock/autosave artifacts (`.#x.py`, `#x.py#`) and
  anything that vanished between listing and reading, because agents create and delete files
  constantly and a gate must never crash on that.
- `tool_targets()` — what to hand an external tool: the whole `src/` path on a full run, or the
  individual changed files.

**`GateResult`** carries `passed`, `threshold`, `actual`, a list of `Diagnostic`s, `duration`, and
two fields that are the point of the design: `error`, set when a *tool* failed rather than the
code (a crashed linter is not a clean bill of health), and `vacuous`, set when the gate passed
because there was nothing to check. A vacuous pass is reported as one; silent under-enforcement is
the failure mode the field exists to name.

**`run_cmd`** is the only subprocess entry point. It never raises: a timeout comes back as return
code 124 and a missing executable as 127, so a hung or absent tool becomes a gate error, not a
traceback inside an agent hook.

**`timed`** decorates every `run()` and fills `duration`.

**Gate order is fixed**, in `config.py`'s `DEFAULT_GATE_ORDER`: protect, static, size, complexity,
boundary, tests, coverage, crap, duplication, mutation, acceptance. A project's `gauntlet.toml`
chooses which gates are enabled by declaring their tables; it cannot reorder them. The order is
cheapest-first so that an agent fixes syntax and shape before it is shown a coverage number, and
so that `stop-check --fail-fast` (the default since `4fc5c34`) ends in seconds when a cheap gate
is red.

**One run at a time.** `exclusive_run` takes an `fcntl` lock on `.gauntlet/run.lock`. Two
overlapping runs would read each other's half-written `junit.xml`, `coverage.json` and `mutants/`,
and report failures that are not real. A second run finding the lock held exits 0 having done
nothing — a concurrent run is not a gate failure. The lock is released when the process dies, so a
leftover `run.lock` file holds nothing.

**Every diagnostic carries a remedy.** File, symbol, line, value, and a sentence saying what to do.
This is a deliberate accommodation of smaller models, which do not infer the fix from the
measurement. Read the message strings in each gate; they are part of the design.

---

## protect

*In one line:* has anyone touched the rules?

*Why it is a gate:* The gate configuration, the approval ledger and the hook settings are hashed,
and the hashes are approved by a human. If any changes without re-approval, everything stops. The
easiest way to pass a gate is to weaken it; this makes that impossible by any route — editor, shell
redirect, subagent. It is the gate that makes the other ten trustworthy, which is why it runs first.

*What it checks:* the configuration files that define what the gates require —
`gauntlet.toml`, `pyproject.toml`, `.claude/settings.json` — have the content a human approved.

*How:* `gauntlet lock` records a SHA-256 digest per file into `gauntlet.lock.json` under
`config:<path>` keys. The gate recomputes the digests (`locking.verify_config`) and reports every
path whose digest moved, was never approved, or whose approval names a file that no longer exists.
Line endings are normalized before hashing (`registry.py`): a CRLF flip is not a change a human
approved.

*Why it exists beside the PreToolUse guard:* the guard only sees file-path tools. A shell redirect,
an editor, a heredoc, or a subagent writes the file without passing through it. Comparing content
against approved hashes is route-independent and catches all of them.

*Config:* `[gates.protect] require_lock = true|false`. Without a lock file the gate **fails open**
(vacuous pass) so that installing Gauntlet does not immediately break a project; set
`require_lock = true` once approvals exist and a missing lock becomes a failure with a remedy.

*Technical notes:* the gate reads the lock through `registry.load`, so a corrupt lock is a gate
*error*, not a pass. It runs first, and under `--fail-fast` a red here stops the run before any
tool is invoked.

## static

*In one line:* is it well-formed?

*Why it is a gate:* A linter and a type checker catch mechanical mistakes before anything expensive
runs. A crashed checker counts as a failure, not a pass: silence is never approval.

*What it checks:* lint (`ruff`) and type checking (`mypy`). Says nothing about behaviour.

*How:* two subprocesses over `tool_targets()`:

- `ruff check --output-format json <targets>` — exit 0 is clean, 1 is findings, anything else is a
  tool failure. Each finding becomes a diagnostic with the rule code as its symbol; fixable ones
  say so.
- `<sys.executable> -m mypy --python-executable <project python> --output json --no-error-summary
  <targets>` — mypy runs under Gauntlet's own interpreter but type-checks against the *project's*
  interpreter, so it sees the project's installed packages. mypy emits one JSON object per line;
  `note` severity is dropped.

*The subtle check:* mypy exits 1 both for "errors found" (with output) and for "no module named
mypy" (without). Exit 1 with empty stdout is therefore treated as a broken tool, not a pass.

*Config:* none. `threshold` is the literal `"clean"`.

*Vacuous when:* there are no Python files under `src/` (the gate says so in its own words, because
mypy's own message for that case sends people looking at mypy).

## size

*In one line:* is it small enough to read?

*Why it is a gate:* Ceilings on function and module length. Long functions are where mistakes hide
and where an agent's edits accrete; a hard ceiling forces extraction before the mess forms.

*What it checks:* every function and method is at most `max_function_lines` long, and every module
at most `max_module_lines`.

*How:* pure standard-library `ast`, no external tool. A `NodeVisitor` walks each file collecting
`(qualified_name, lineno, end_lineno − lineno + 1)` for every `FunctionDef` and `AsyncFunctionDef`,
descending through classes so methods are reported as `Class.method`. Module length is
`len(source.splitlines())` — physical lines, including blanks, comments and docstrings. Function
length is likewise the physical span from the `def` line to the last line of the body: the
docstring counts, decorators do not (`ast` puts `lineno` on the `def`, below any decorators).

*Why:* long functions and modules are where agent edits accrete. Measuring with `ast` means no
dependency and no disagreement with a formatter.

*Config:* `max_function_lines` (default 25), `max_module_lines` (default 300; ClaimGate runs
250). `actual` reports the worst function; module violations appear as diagnostics only.

*Technical notes:* a file that does not parse returns no functions rather than crashing — the
static gate reports the syntax error, and this gate should not report it a second time. The same
rule applies in boundary. A file that vanishes or is not UTF-8 is skipped.

## complexity

*In one line:* how many paths through this function?

*Why it is a gate:* Cyclomatic complexity is a count: one, plus one for every `if`, loop, `and`/`or`
and exception handler. A score of 6 means roughly six routes through the function, each needing a
test. The default ceiling is 6 — strict on purpose; convention starts worrying at 10. Size and
complexity together bound both dimensions: not long, and not tangled.

*What it checks:* cyclomatic complexity per function and method is at most `max`.

*How:* `radon cc --json <targets>` via `artifacts.radon_blocks`, shared with the CRAP gate so
radon runs once per gate invocation of each. radon's JSON is a dict of file → list of blocks; each
block has `name`, `classname`, `type`, `lineno`, `endline`, `complexity`. `judge()` is pure: it
takes the parsed payload and the ceiling and returns the worst score and one diagnostic per block
over it. radon reports a per-file parse error as a dict instead of a list, and those entries are
skipped for the same reason as in size.

*What cyclomatic complexity is, as radon computes it:* one plus the number of decision points in
the function — `if`, `elif`, `for`, `while`, `except`, `with`, boolean operators (`and`/`or` each
add one), comprehension conditions, and each `case`. It counts *branching*, not size or nesting:
a flat function with six guard clauses scores the same as six nested `if`s. That is the intended
reading; the size gate handles length, and the two together bound both dimensions.

*The comparison is strictly greater-than*, so a function exactly at the ceiling passes. The
default ceiling is 6, which is low by conventional standards (10 is the usual "start worrying"
figure) and deliberate: it forces extraction early, which is the shape of code an agent can edit
safely.

*Config:* `max` (default 6).

*Vacuous when:* no Python files. A radon failure (no output, unparsable output) is an `error`.

## boundary

*In one line:* do the acceptance tests describe behaviour or implementation?

*Why it is a gate:* Step definitions may reach the system only through a small test-API layer, never
by importing internals. A test bound to internals breaks on every refactor, which trains people to
stop trusting tests. This rule once lived in a prompt; it became a gate because rules in prompts are
forgotten.

*What it checks:* step-definition files under the acceptance steps directory import nothing from
the production source tree directly. They reach the system only through a test API package.

*How:* pure `ast`. `production_packages(src)` lists the top-level importable names under `src/`
(packages with `__init__.py`, and bare modules). Each step file is parsed and every absolute
`import x` / `from x import y` is reduced to its top-level name; relative imports are ignored
because they stay inside the test tree. A step file importing a production package name is one
diagnostic per import, naming the module and the test-API directory to use instead.

*Why:* acceptance tests that import internals overfit to the implementation and rot with every
refactor; a stable test-API layer keeps them describing behaviour. The docstring says the rule
"previously lived only in a prompt — and a rule that lives in a prompt is exactly what this tool
was built to replace."

*Config:* `steps` (default `tests/steps`), `api` (default `tests/api`; used only in the remedy
text — the gate does not verify that imports go *through* the API, only that they do not go
*around* it).

*Vacuous when:* no steps directory, or no source packages.

*Technical note:* `actual` is `"<n> step file(s), <m> direct import(s)"`, and the count of step
files is a useful check that a new acceptance module was picked up (ClaimGate watched this go
16 → 17 when a spec was added).

## tests

*In one line:* does the suite pass?

*Why it is a gate:* With one non-obvious rule: an empty suite fails. Otherwise deleting the tests
directory is a valid way to go green.

*What it checks:* the unit/acceptance suite passes, and **an empty suite fails**.

*How:* one `pytest <tests> -q --junitxml=.gauntlet/junit.xml` run under the *project's*
interpreter. If the coverage or CRAP gate is enabled, the same command also carries
`--cov=<src> --cov-branch --cov-report=json:.gauntlet/coverage.json`, so the suite runs once and
three gates read its artifacts. The gate parses the JUnit XML rather than pytest's stdout: counts
from every `<testsuite>` element, one diagnostic per failed `<testcase>` with the failure message
as headline and the last 25 lines of the traceback.

*The empty-suite rule:* pytest exits 5 when nothing was collected; the gate turns that into a
failure with a remedy. Otherwise deleting the test directory would be a valid way to go green.

*Technical notes:*

- `_failure_node` is written longhand because an `Element` with no children is falsy, so
  `case.find("failure") or case.find("error")` silently loses failures.
- Exit codes other than 0/1, or a missing `junit.xml`, are a gate error (pytest crashed, plugin
  missing).
- `passed` requires both zero failures/errors *and* exit 0.

*Config:* none; `threshold` is `"all passing"`.

## coverage

*In one line:* did the tests run the code?

*Why it is a gate:* Line and branch percentages. The weakest gate, and knowingly so: coverage proves
lines executed, not that anything was checked. The next two exist because of that.

*What it checks:* aggregate line coverage ≥ `line`; aggregate branch coverage ≥ `branch` if set;
every file ≥ `per_file_min` if set.

*How:* reads `.gauntlet/coverage.json` written by the tests gate. **Runs no subprocess.** If the
artifact is missing the gate errors with a message pointing at gate order or `--gates` selection
(the tests gate must have run in the same invocation). Branch percentage is computed from
`covered_branches / num_branches` in `totals` and omitted when the project has no branches.

*The design rule in `judge()`:* every diagnostic corresponds to a rule that is actually enforced.
With `per_file_min` unset the gate judges the aggregate only and says nothing about individual
files — so a passing gate never emits per-file guidance an agent could mistake for a failure.
When `per_file_min` is set, files are reported worst-first with up to ten missing line numbers.

*Config:* `line` (default 90), `branch` (optional), `per_file_min` (optional).

## crap

*In one line:* is there a complex function nobody tested?

*Why it is a gate:* A real metric (Change Risk Anti-Patterns) combining complexity with per-function
coverage. A simple function passes at any coverage; a complex one passes only when thoroughly
tested; a very complex one cannot pass at all and must be broken up. It catches what the two inputs
miss on their own: a well-covered *file* hiding one untested, complex *function*. The failure
message computes the exact coverage that would fix it.

*What it checks:* per function, `CRAP = CC² × (1 − coverage)³ + CC ≤ max`.

*Why the formula:* complexity and coverage gates each miss the dangerous intersection — a complex
function inside a well-covered file. CRAP encodes the judgement that complexity is acceptable only
when proven: at 100% coverage the cubic term vanishes and CRAP collapses to CC; at 0% coverage
complexity is punished quadratically. The default ceiling 15 with a complexity ceiling of 6 means
a CC-6 function needs about 50% coverage to pass and a CC-3 function passes at any coverage.

*How — the join:* radon blocks (from `artifacts.radon_blocks`, shared with complexity) are joined
to `coverage.json`'s per-file `executed_lines` / `missing_lines` by path. Paths are normalized to
root-relative POSIX strings (`normalize()`), because radon reports paths as invoked (often
absolute) and coverage.py reports them relative. Only blocks whose radon `type` is a function or
method are scored; classes are not. Files radon saw but coverage did not are skipped, not scored
as zero.

*Per-function coverage:* `span_coverage` takes the block's `lineno..endline` span and computes
`executed ∩ span / (executed ∩ span + missing ∩ span)`. The denominator is *statements*, not
physical lines: blanks, comments and continuation lines are neither executed nor missing, so
counting them would understate coverage. A span with no statements at all is treated as fully
covered.

*The remedy is computed, not templated:* `required_coverage(cc, ceiling)` solves the formula for
the coverage that would bring the function under the ceiling —
`1 − ((ceiling − CC) / CC²)^(1/3)` — and the diagnostic says "cover it to at least N%". When
`CC > ceiling` no coverage helps (CRAP is never below CC) and the remedy says so: extract functions;
tests alone cannot fix this.

*Config:* `max` (default 15.0). Requires both radon and the coverage artifact; either missing is an
error.

## duplication

*In one line:* did the agent write this twice?

*Why it is a gate:* A clone detector, aimed at a failure specific to agents: one that cannot find
the existing helper writes a second, and every individual edit looks fine in review.

*What it checks:* the number of token-level clones reported by `jscpd` is at most
`max_duplicate_blocks`.

*How:* `jscpd <targets> --reporters json --output .gauntlet/jscpd --min-lines N --min-tokens M
--silent`, then the JSON report's `duplicates` array, ordered largest clone first. Each becomes a
diagnostic at the first occurrence naming the second.

*Why jscpd:* language-agnostic, so the same gate will serve a non-Python adapter; and duplication
is a specifically agentic failure — an agent that cannot find the existing helper writes a second
one, and every individual edit looks fine.

*Config:* `max_duplicate_blocks` (default 0), `min_lines` (default 5), `min_tokens` (default 50).
jscpd requires Node; a missing executable (return code 127) produces an install hint as the gate
error, and a run that leaves no report is an error too.

## mutation (code)

*In one line:* would the tests notice if the code were wrong?

*Why it is a gate:* Hundreds of small deliberate changes are made to the code — a `<` becomes `<=`,
a constant changes, a line is removed — and the tests run against each. A change the tests do not
catch is a "surviving mutant": behaviour that is untested. This is what makes coverage honest.
Survivors that provably cannot change behaviour are reviewed by a human and recorded, and count as
killed.

*What it checks:* the unit tests notice when the code behaves differently. Coverage proves lines
ran; a test that calls a function and asserts nothing has full coverage and kills no mutants.

*How:* `mutmut run [module filters]` under the project interpreter, then `mutmut results`, both
through `adapters/python.py`. mutmut copies `src/` into `mutants/`, rewrites each function into
one variant per mutation site, and runs the suite against each. `mutmut results` lists only
unkilled mutants, so the killed count is derived: total − survivors. Buckets `skipped` and
`suspicious` are not survivors.

*Scope:* with `scope = "changed"` (the default) and a `--changed` run, only modules touching
changed files are mutated (`python_adapter.module_filter`); with nothing changed the gate passes
vacuously as "no changed modules". On a full run (`changed_files is None`) every module is
mutated regardless of `scope`.

*Survivors are described, not just named.* For each survivor (up to 40) the gate runs
`mutmut show <name>` and extracts the first removed and first added line of the diff, so the
diagnostic reads "`x == y` → `x != y` in `function`". The ID alone tells an agent nothing.

*Identity and the ledger:* mutmut names mutants positionally (`x_calc__mutmut_63`), so the number
shifts whenever the function changes. Gauntlet keys a code mutant on
`module|function|removed_line|added_line`, which survives unrelated edits. Survivors are classified
against `gauntlet.lock.json` under the single subject `code`: a survivor with an approval is
*reviewed-equivalent* and counts as killed in the score; one without is *unresolved* and is a
diagnostic; an approval whose mutant no longer survives is *stale* — reported as housekeeping,
not a failure, with the remedy `gauntlet mutant prune-code`.

*Score:* `(killed + equivalent) / (killed + equivalent + unresolved)`, 100 when there is nothing to
mutate. `passed` is `score ≥ min_score`, and additionally *no* unresolved survivor when
`require_review = true`.

*Config:* `min_score` (default 90), `require_review` (default false), `scope`, `timeout` (default
1800 s).

*Technical notes:* mutmut's copy of the source tree fails on a dangling editor lock file; the gate
recognizes that traceback and prefixes an actionable hint. The findings file records that mutmut's
own coverage-guided test selection can go stale (a cached mapping reporting 100% after the
protecting test was deleted); projects that care run the gate cold by clearing `mutants/` first.

## acceptance

*In one line:* does the code do what the specification says, and does the specification itself
check anything?

*Why it is a gate:* Specifications are plain-language scenarios a human approves and locks. Every
spec must be approved and unchanged; every scenario must pass; and then the gate *mutates the
specification's own example values* and demands the scenario fail. If the expected outcome in a row
changes and the test still passes, that row was decorative. This turns a spec from documentation
into a contract.

*What it checks:* three stages, in order, on every feature file under `features/`:

1. **Approval.** Every spec is in the lock with its current SHA-256 (`specs.verify`). An
   unapproved or modified spec fails the gate before anything runs, with the remedy
   `gauntlet spec approve`.
2. **Baseline.** `pytest <steps> -q --no-header -p no:cacheprovider` under the project interpreter
   passes. A failing scenario fails the gate here, with the first 800 characters of pytest's output.
3. **Mutation.** Every mutant of a specification value must make the suite fail. A surviving mutant
   means the scenario passes regardless of the values it claims to test, which makes it decorative.

*Stage 3, how:* `acceptance/gherkin.py` parses the feature into an IR that records source
positions; `acceptance/mutation.py` enumerates mutants; the gate applies each **to the real
feature file in place**, runs the acceptance suite, restores the original, and records survivors.

*What gets mutated:*

- Every cell of every `Examples:` row. The replacement is chosen to discriminate, not to be noise:
  booleans flip (`true`↔`false`, `yes`↔`no`, `on`↔`off`, case-insensitive, replacement lowercased);
  a bare number is perturbed by one; otherwise the cell takes the value of the same column in the
  row *most different* from this one (most columns differing), falling back to appending
  `_gauntlet` when no sibling has a different value. Number handling is pre-emptive: a numeric
  cell is never sibling-swapped.
- Every quoted string and bare number in a step's own text (`LITERAL_PATTERN`), in plain scenarios
  *and* outlines. Placeholders `<name>` are never matched. The replacement is the same rule; for a
  string with no siblings it is the `_gauntlet` suffix.
- **Not** Background steps, and **not** unquoted enumerations in a step (`the state is TRIAGED`).
  These are the two places the findings file calls fixed Givens: mutation cannot reach them, and a
  well-designed spec puts anything it wants protected into an Examples cell.

*Identity:* a spec mutant's locator is structural — feature key, scenario name, column, and the
row's values — deliberately not line-based, so inserting a scenario above does not lapse every
approval. Its *signature* (`old->new`) can change when a neighbouring row changes the sibling
choice while the locator holds.

*Cost:* each mutant runs the **entire steps directory**, not just the mutated spec's module. Wall
time is therefore (total mutants) × (whole-suite time), and grows with every row added anywhere.
On a fifteen-spec project this reached ~2,900 s. `mutation_sample = N` caps the mutants per feature
(sampled with a fixed seed, `sample()`), trading completeness for time; the honest fix is scoping
the per-mutant run to the mutated spec's module, which is an open design question because it
changes what a cross-file kill means.

*Safety of in-place mutation:* the original is written to `.gauntlet/mutation-backup/<file>`
before the first mutant and restored in a `finally`. A clean interrupt (SIGINT) restores; a hard
kill between write and restore leaves a mutant on disk, and the backup — or `git checkout --
features/` when every spec is committed at its locked text — is the recovery.

*Classification and reporting:* survivors are classified against the lock under `spec:<path>`
exactly as code mutants are (equivalent, unresolved, stale). Diagnostics are grouped **one per
scenario**, listing up to six of its surviving values, because thirteen identical sentences burn
the diagnostic budget and the hook's character cap for no signal. `actual` reads
`"<n> spec(s), <m> surviving mutant(s), <k> reviewed-equivalent"`; a green summary omits the
killed count.

*Config:* `features` (default `features/`), `steps` (default `tests/steps`), `require_approved`
(default true), `mutate_examples` (default true), `mutation_sample` (default 0 = all), `timeout`
per suite run (default 600 s).

*Vacuous when:* no feature files.

*Public seams:* `survivors_for` is public so that `gauntlet mutant list/approve` share the gate's
exact code path — the CLI must never disagree with the gate about what survived.

**The trade.** Everything past the first gate is automated and runs on every turn. The human
reviews two artifacts — the specifications, in plain language, and the short list of mutants
declared equivalent — and never has to read the code to know it is right. The gates cost machine
time, not review time.

---

## The stop hook, in one paragraph

`gauntlet stop-check` runs every enabled gate over the whole tree (never `--changed`, which passes
vacuously when nothing changed and is wrong for "are you actually done"), under the run lock,
stopping at the first failure by default. Exit 2 blocks the agent's stop and feeds the report
back; after `--max-attempts` bounces it exits 0 with a `systemMessage` so a human decides. It emits
`gate.finished` lines to `.gauntlet/events.jsonl` but neither `run.started` nor `run.finished`
(a known gap in the findings file). It records no tree hash, so it cannot itself skip a run on an
unchanged tree; a project wanting that wraps the hook.

## Reading a gate quickly

Each gate file is organized the same way: constants and defaults at the top; a pure `judge()` or
equivalent that takes parsed data and returns `(actual, diagnostics)` and is what the unit tests
exercise; small `_diagnostic` builders whose message strings are the remedy; and a thin `run()` at
the bottom that reads config, gathers input, handles the vacuous and error cases, and calls
`judge`. If you want to know *what a gate measures*, read `judge`; if you want to know *what it
runs*, read `run` and the command it builds; if you want to know *why*, read the module docstring
and the message strings.
