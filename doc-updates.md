# Documentation updates — the settled plan (August 2026)

Apply on the audit branch (or on main after merging it). Three files change: README.md,
BACKLOG.md, ARCHITECTURE.md. Each block below is drop-in replacement or addition text; the
splice instruction precedes each block. Written to the repo's prose standard (ASD-STE100 as
adapted in docs/audit.md section 3).

Branch note, for whoever applies this: merge the audit branch into main first — it is
behavior-neutral and green. Then re-cut the v2 branch from main, because the existing v2 branch
predates the audit and carries the stale documentation the audit fixed.

---

## 1. README.md — replace the entire "Roadmap" section

Also delete the separate "Planned work" section if it still exists after the audit's step 1,
and move anything in it that is still open into BACKLOG.md (section 3 below). The repo keeps
one list of open work, and BACKLOG.md owns it. The roadmap owns the version narrative only.

```markdown
## Roadmap

Open work lives in [BACKLOG.md](BACKLOG.md), with the evidence behind each item. This section
only describes where each version line is going and where the product's boundary sits.

### v1 — a usable single-agent harness for Python (current)

Eleven gates, the approval ledger, hooks, status and review, the event log. Proven on two
projects: this repository, and an FNOL intake service built end to end under the gates. What
remains is polish, not capability: systematic root-cause diagnostics, mutation cost that is
visible and boundable, and validation on a project someone actually wants. The v1 line is done
when every gate can run on a project it fits without being weakened to pass.

### v2 — the workspace

The bottleneck today is the human's surface, not enforcement. Review is a terminal walk, and
"what is waiting on me" is a command you must think to run. The workspace shows live gate
progress, the approval inbox, and diffs in context, with one-click approve.

Two rules make it safe to build. The workspace is a **client**: it reads the event log and the
JSON contract, and nothing else. If it needs data the contract does not provide, the contract
grows — the workspace never gets a private path into internals. And the workspace **approves
through the same ledger operations** as the CLI, with the same required reason and reviewer. A
surface that could approve without the ceremony would turn the ledger into a rubber stamp.

### v3 — the substrate for orchestration

Multi-agent harnesses describe workflows as state machines, and every transition needs an
answer to "has this actually happened?" A supervisor agent that answers by inspection inherits
the prompt decay the gates exist to eliminate. Gauntlet already answers most transition
questions deterministically. Three small additions make that explicit:

- **Named gate profiles** — `[profiles] cleaning = [...]` — so a workflow state's exit criteria
  has a name instead of an ad-hoc gate list.
- **Work-item identity** — an ID threaded through every event, so the log reads per-story
  rather than per-project.
- **A transition query** — which profiles currently pass, as JSON.

### The orchestrator is a separate application

Everything above the substrate — scheduling, finite-state machines that direct agents, watchdog
timers, transient agent lifecycles, roles and constitutions, squad leaders, worktrees, and
concurrency — belongs to an orchestrator that **uses** Gauntlet and does not live in it. This is
a boundary, not a deferral.

The reason is the same ownership rule that shapes everything else here: anything a supervisor
must *trust* has to be deterministic, so it lives in Gauntlet. Everything that is judgment,
sequencing, or conversation lives above. Gauntlet's commitments to whatever sits on top: the
exit-code contract, the JSON report, the versioned event log, and (in v3) profiles and the
transition query. Gates stay non-interactive and route-independent, so a verdict never depends
on who — or what — asked for it.
```

---

## 2. ARCHITECTURE.md — add this subsection at the end of "Contracts you must not break"

```markdown
### The boundary above Gauntlet

An orchestrator — anything that schedules agents, runs state machines, applies watchdogs, or
manages roles and handoffs — is a separate application that consumes Gauntlet. It talks to
Gauntlet only through the public contract: exit codes, the JSON report, the event log, and (once
v3 lands) named profiles and the transition query.

Two rules follow, for anyone tempted to blur the line. Nothing in this repository may take a
dependency on any particular orchestrator, and no gate may behave differently because an
orchestrator invoked it — a verdict that depends on the caller is not a verdict. And when an
orchestrator needs something Gauntlet does not expose, the answer is to extend the contract
(an event kind, a JSON field, a query), never to import Gauntlet's internals. `loop.py` is the
deliberate ceiling of orchestration inside this repo: one prompt in, files out, no memory, no
roles.
```

---

## 3. BACKLOG.md — add this section directly under the header, before P1

Renumber or fold existing open items into it as appropriate; anything the audit's step 1 marked
done stays in the Done section. This becomes the single list of open work (the README's
Planned-work section is deleted per section 1 above).

```markdown
## Current open work (post-audit, August 2026)

The v1 finish line, in intended order. Items marked **[human]** need a decision or a
`gauntlet lock` that only the human can supply.

1. **Audit close-out.** Commit `docs/audit.md` (repairs the dangling reference in
   `report.summary_line`'s docstring). Verify the scaffolded hook shape against Claude Code's
   current hooks schema (audit O5) — if the exec form is wrong, the hooks fail open and this
   outranks everything else on the list. Resolve `summary_line` (audit O1/O2) **[human]** and
   this repo's enabled-but-vacuous acceptance gate (audit O3) **[human]**.
2. **Root-cause diagnostics as a pattern.** Three instances were fixed by hand; the discipline —
   every gate distinguishes "tool failed", "tool found nothing", and "nothing to measure", and
   names the upstream cause — is not yet systematic. Gate-by-gate sweep, one table-driven test
   per fixed case.
3. **Mutation cost management.** In order: surface mutant counts and elapsed time in the gates'
   summaries so cost is visible before it hurts; decide whether sampling defaults change
   **[human]**; design the survivor cache before building it — a stale cache entry that reports
   a killed mutant which would now survive is silent under-enforcement, so the design doc must
   show why that cannot happen, and gets reviewed before code exists.
4. **Real-world validation.** Build something someone wants, under the gates, and fold what
   breaks back into this list.

v2 (workspace) and v3 (substrate) items live in the README roadmap until work starts on their
branches; when it does, their open items move here.
```

---

## 4. Consistency sweep (same commit as the above)

- Grep README and ARCHITECTURE for any remaining sentence that lists FSMs, watchdogs, roles, or
  transient agents as Gauntlet features or Gauntlet plans; rephrase to name the orchestrator as
  a separate consumer. The "Also planned" paragraph at the end of the old roadmap is the likely
  offender alongside anything the external review's vocabulary leaked in.
- Confirm `loop.py`'s docstring still matches the new ARCHITECTURE subsection (it should — the
  subsection was written from it).
- The second-language adapter (C#) stays listed once, in the roadmap or BACKLOG, not both.
```
