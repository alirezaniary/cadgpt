# Checkpoint — 2026-09-03, coordinator session 4 in progress

Session 2 settled scope and moved no code. Session 3 closed five tasks with their reviews —
T-0025, T-0028, T-0027, T-0029 and T-0030. **Session 4 closed T-0031, T-0032, T-0051 and T-0033 with their
reviews — every task from its brief, plus the one its own reviews raised above them.** `main` is green and every task file
carries its evidence. `docs/plan.md` is the route and `docs/tasks/` holds
the detail; this file only records where the loop is and what is unresolved.

## The MVP, settled in session 2 — do not re-litigate

> The user uploads a model, picks which rules to run it against, and gets back a report file.

Rules are a catalogue we ship, not a file the architect uploads (the catalogue is a **separate
model** from the tenant-owned `RuleSet`, so `for_tenant` stays total). The first iteration
**reports and does not act** — overlay, marked sheets and BCF are out by decision, which takes
gate 2 off the critical path. The deliverable is a generated **Markdown** report whose URL sits
on the job record. The upload ceiling is **measured against peak worker memory**, not chosen.
Full reasoning in `docs/decisions.md` and `prd.md` §12.

## Where the loop is

| Task | State | Commit |
|---|---|---|
| T-0024 — browser evidence harness | done | `c9d351f` |
| T-0026 — requirement description from `to_string` | done, reviewed | `b38b15a` |
| T-0028 — a requirement that evaluated nothing must not report PASS | done, reviewed | `6e64ce2` |
| T-0025 — report presentation | done, reviewed, fix-now applied | `ec9b761` |
| T-0027 — requirement as structured citation | done, reviewed, fix-now applied | `f66a136` |
| T-0029 — say what was checked | done, reviewed, fix-now applied | `3a87ef5` |
| T-0030 — the rule catalogue | done, reviewed — **no fix-now** | `9faf208` |
| T-0031 — rule selection on the run | done, reviewed, 4 fix-now applied | `25e49ac` |
| T-0032 — the Markdown report file | done, reviewed, 3 fix-now applied | see log |
| T-0051 — a report that never generated can be recovered | done, reviewed | `7ede740` |
| T-0033 — the measured upload ceiling | done, reviewed | `b532f3f` |
| T-0034 … T-0066 | queued from reviews | — |

Numbering continues at **T-0067**.

**All three clauses of the MVP sentence exist in code, and T-0033 closed the last task of the
brief.** Phase 3 is still deliberately *not* marked done — thirty-three queued findings remain, and
three of them bear on whether the sentence holds for a real user rather than in principle:
**T-0056** (a lost dispatch strands the check itself at PENDING, and `MAX_IN_FLIGHT_RUNS = 1` means
that row blocks the review forever), **T-0062** (an ordinary deploy burns a run's claims, so a
healthy model can be refused and told the wrong reason) and **T-0053** (the download button a user
would actually press has never been executed).

One clause is recorded as **NOT DONE** rather than claimed: the ceiling is derived from worker
memory, but *"high enough to serve 95% of users"* rests on a single 47MB sample and cannot be
settled without a model corpus we do not have.

`make verify` at last run (after T-0033): ruff clean, `mypy --strict` over 156 files, **5 import
contracts kept**, **235 tests passed**, frontend build green. `make e2e` green (3 specs).

## Nothing is unresolved

Every closed task carries its review. **Phase 3 is not complete** — T-0033 is written and
undispatched — but nothing is half-finished and no review is outstanding.

Next: **T-0051** (a report that never generated cannot be recovered — it undercuts the MVP sentence
more directly than anything else queued), then **T-0033** (the measured upload ceiling, task file
written), then the rest of T-0034…T-0055.

**The pattern to carry forward, now three reviews deep and unbroken: the builders' mechanisms were
sound every time, and every defect was in a claim about coverage or honesty that the suite was
green over.**

T-0030's review nearly *was* lost — it was dispatched as the session ended and landed in the last
moments. A note claiming it had been lost was written and is now removed. The near-miss is worth
remembering: **dispatch a review with enough session left to receive it**, or the task carries an
unreviewed commit into the next session, which is what happened to T-0025 twice.

## What the reviews changed, so nobody re-derives it

**T-0025's review finally ran** — it had been lost with session 1 and pre-empted in session 2.
Worth recovering, and instructive about where to point a reviewer: the **filter**, which the
hunt list was written to distrust, came back clean under all four of its undriven states. Both
defects were in **coverage**, the thing the task existed to add. The headline sentence was a
constant — `specifications_passed + specifications_failed + specifications_indeterminate` is
identically `specifications.length` for every report the engine can produce — so it read "N of
N" always, claiming full coverage above a block naming the specifications that checked nothing.
And `establishedNothing()`'s `matched === 0` disjunct swallowed `NO_SUBJECTS_BUT_REQUIRED`,
labelling an established FAIL as unevaluated. Both now derive from **one predicate**, so they
cannot disagree on screen, and the predicate reads the reason code `judge()` already assigned
rather than holding a second copy of the engine's judgement in TypeScript.

**T-0028's review proved the dangerous direction by exhaustion, not sampling** — a requirement
can reach all-zero counts only via a prohibited specification or an empty applicable set, both
of which genuinely evaluated nothing, so no real PASS can become an unknown. It then found the
evidence block's claim that the flipped status "renders through the existing `StatusPill`"
to be false: `requirement.status` is read by **no component**. T-0028 is real in the API and
invisible in the browser until **T-0037**.

## What session 4's review found, added to the pattern

T-0031's review repeated session 3's shape exactly and sharpened it. **The mechanism was sound and
the intricate surfaces held under attack** — tenancy, the narrowed `select_for_update(of=("self",))`,
and the three-valued combination across packs were all specifically hunted and all came back
clean. **The defect was in a claim about honesty**, again, and again the suite was green over it:
`checksum_sha256` was written by one function and read by nobody, so a run could succeed, flip
`FAIL` to `PASS`, and store a citation naming a pack and hash it had not checked.

The new lesson is about **evidence that cannot fail**. Two of T-0031's evidence items asserted
proof they were structurally incapable of delivering:

- the worker log line that proved "the check ran against the cited rules" was **built from the
  citation**, so it could only ever agree with the citation — the selection JSON echoed back;
- the reproducibility test mutated the catalogue by seeding a **new row**, which a plain
  `ForeignKey` would pass identically, so it established nothing about the snapshot-versus-FK
  choice it existed to justify.

Neither was a lie about what was run. Both were real commands with real output that could not have
come out differently if the code were broken. **Ask of every evidence item what it would look like
if the thing were broken** — if the answer is "the same", it is not evidence. This is a sharper
test than "did the builder actually run it", and it caught what re-running would not have.

Both are now fixed: the log line carries the produced report's own `ids_title` and specification
names beside the cited identity, so it *can* disagree, and disabling the checksum comparison
prints `cited_name: "Accessible door width"` against `evaluated_ids_title: "Door name recorded"`
over an outcome of `PASS`.

## Two decisions settled this session, in `docs/decisions.md`

- **A requirement that evaluated nothing is explained, never suppressed.** The tidy-up — hiding
  the row when the specification reached its verdict without evaluating requirements — is
  refused. Hiding a row that says "nothing was checked here" is the failure I7 exists to close.
- **A verdict-changing engine release bumps the engine version.** Schema version answers "can
  this be parsed"; engine version answers "would this be judged the same way today". Old runs
  are never re-run to match — a run is a record of what was said at the time.

## What every review this session actually found

The pattern is worth carrying forward, because it is not the one the hunt lists predicted. **The
builders' mechanisms were sound every time; the defects were all in claims about coverage and
honesty** — and none was caught by the suite.

- A coverage headline that was arithmetically incapable of saying anything but `N of N`.
- A `PASS` returned over zero evaluations.
- A citation that resolved to the **wrong rule**: `enumeration` joined with "and", so a choice of
  two values read as a demand for both.
- An unrecognised operator degrading to a confident sentence rather than a visibly unresolved one.
- A disclosure promising a single source that its consumer could never read.

Twice the review's own hunt list was pointed at the wrong surface — T-0025's filter came back
clean under all four undriven states while coverage, the thing the task existed to add, was wrong
twice. **Point reviews at what the task claims to establish, not at what looks most complex.**

## Do not take a builder's evidence on trust

Of the last ten evidence blocks: two contained tests that passed with their own fix reverted, and
**four contained a claim that was false** — a Python test asserted to exercise a TypeScript
function, a `StatusPill` rendering path that has never existed, a reassurance attached to exactly
the case that was broken, and a `NOT DONE: nothing` over a promise that could not be kept.

**Re-run the mutation yourself. Open the screenshot.** Every one this session reproduced exactly:
`3 of 3` where the fix renders `2 of 3`; `Status.PASS` over `0/0/0`; `and` where the fix renders
`or`; `KeyError: 'totalDigits'`; `Expected "disclosure" / Received "coverage"`; a gutted
disclosure caught by its new wording assertion; and four tests failing when `RulePack` was made
tenant-owned.

## Environment notes that cost time to discover

- The `builder` and `reviewer` agent types **became dispatchable partway through session 4** and
  were used directly for T-0033's review. Earlier in that session they were not registered and the
  workaround was `general-purpose` told to read `.claude/agents/builder.md` or `reviewer.md` as its
  role contract. Try the real types first; the workaround still works if they are absent. Builder on
  sonnet, reviewer on opus.
- **The engine CLI is `uv run cadgpt-check <model.ifc> <rules.ids> --json`.** T-0026, T-0027 and
  T-0028 all shipped a task file instructing the builder to run `cadgpt-engine check`, which
  does not exist. Fixed in all three; do not reintroduce it.
- A frontend change reaches the served page only after
  `docker compose -f deploy/compose.yaml up -d --build web`. That invocation also rebuilds and
  recreates `cadgpt-api-1`, so it picks up `services/api` and `packages/engine` too.
- `ruff format` no longer scans `docs/**`. It was rewriting quoted defects inside task files
  into different code, and a code quote in a task file is evidence.
- A long-running builder can be killed mid-task by a session usage limit. Its working tree
  survives intact; resume the same agent rather than re-dispatching, so its context is not lost.
- A long-running builder killed by a session usage limit leaves its working tree **intact**.
  Resume the same agent by name rather than re-dispatching, so its context is not lost. This
  happened twice this session and both resumes worked cleanly.
