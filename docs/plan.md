# Plan — from a checking engine to a product that can carry one

**What this is:** a multi-tenant SaaS where a design office uploads an IFC model and an IDS
rule set and gets back a report of what passes, what fails, and what could not be
determined. Rules are data — no building code is baked in.

Status of each phase is recorded here as it completes. `docs/decisions.md` holds the
reasoning; `prd.md` is the product source of truth.

---

## Phase 0 — Prove the toolchain — **DONE 2026-09-01**

Nothing in the repository had ever run an IDS against an IFC. Everything downstream assumed
it worked. It does:

| Model | Rules | Time | Result |
|---|---|---|---|
| Duplex 2.3MB (US) | Wooden Windows (NL) | 1.4s | 46 fail — correct, wrong standard for the model |
| Schependomlaan 47MB (NL) | BIM Basis ILS (NL national standard) | 9.9s | 7 pass / 3,623 fail |
| Schependomlaan 47MB | Hand-written "door ≥ 900mm" numeric rule | 5.4s | 92 pass / 113 fail |

Of 113 reported door-width failures, only 12 doors are too narrow; 101 have no width
recorded. Separating those is the product's whole value-add.

## Phase 1 — Reset the repository — **DONE 2026-09-01**

`main` reset to `942b45f`; the nine commits after it discarded. Recovery branch:
`backup/pre-reset-20260901`. Detail in `docs/decisions.md`.

## Phase 2 — The modular monorepo — **DONE 2026-09-02**

The plan at this point called for the thinnest possible Django app: one screen, synchronous,
no tenancy, no queue, no separate frontend. That was reversed deliberately — see
*"A base built to be continued, not a prototype to be thrown away"* in `docs/decisions.md`.
What exists now:

```
packages/engine/     cadgpt_engine — deterministic checking. No framework, no network.
services/api/        Django + DRF + Celery. Six apps, layered by import contract.
services/web/        React + Vite + TanStack Query. TypeScript, RTL-native.
deploy/              Dockerfiles and the compose stack.
```

**Verified running 2026-09-02**, on the container stack, not in a test harness:

```
POST /api/v1/auth/register/          201, account created
POST /api/v1/auth/login/             200, access token in body, refresh in an httpOnly cookie
POST /api/v1/tenants/                201, tenant + owner membership in one transaction
POST /api/v1/media/       (IDS)      201, sha256 recorded, stored under the tenant's prefix
POST /api/v1/rule-sets/              201, IDS parsed: title "Accessible door width", 1 spec
POST /api/v1/media/       (IFC)      201
POST /api/v1/reviews/                201
POST /api/v1/reviews/{id}/check/     202 accepted, run pending
   -> Celery worker, separate container, 0.511s
GET  /api/v1/reviews/{id}/runs/{id}/ 200, status succeeded, outcome FAIL
                                     1 PASS / 1 FAIL / 1 INDETERMINATE
```

The three doors came back as three different answers: one compliant, one measured at 800mm
against a 900mm requirement (`ATTRIBUTE_VALUE_MISMATCH`, FAIL), and one with no width
recorded at all (`ATTRIBUTE_EMPTY`, INDETERMINATE). That distinction, surviving the whole
stack from upload to JSON response, is the thing being built.

Three defects were found by running it that the test suite had not caught, each now covered
by a test: tenant resolution ran as middleware and could never see a JWT-authenticated user;
JWT lifetimes were configured as integers and failed on the first real sign-in; the report
named the storage key instead of the file the architect uploaded.

## Phase 3 — What the first real user needs — **IN PROGRESS**

**Scope settled 2026-09-02 by the product owner.** Four direction questions were answered
and written to `docs/decisions.md` and `prd.md` 12. The phase got smaller in three places and
larger in one, and the ordering below is no longer a guess about what a user hits first — it
is the shape of the MVP.

The MVP is one sentence: **the user uploads a model, picks which rules to run it against, and
gets back a report file.**

- **The rule store.** Rules are a catalogue we ship, not a file the architect uploads.
  Existing public IDS sets seeded so development does not wait on authoring; the user selects
  by jurisdiction, region and version; the selection is part of the job record. Authored packs
  — Iranian building code first, then EU and US — arrive in a separate thread and are not this
  loop's work. This loop builds the store, the metadata, the selection and the seeding path.
  Pulled forward out of Phase 4 (`prd.md` 5.5) in its metadata-and-selection form only: no
  clause records, no YAML compilation, no ratification pipeline. A shipped pack belongs to no
  tenant, so it is a separate model from the tenant-owned `RuleSet` — a nullable `tenant`
  column at the centre of the one structurally-enforced invariant is not a trade worth making.

- **The report as a file.** The job record carries the URL of a generated Markdown report.
  Markdown because it survives the tooling, renders where the office already works, and needs
  no layout engine. The presentation rules already built — coverage before findings,
  FAIL → INDETERMINATE → PASS — are what the generator implements. The in-app React view stays
  beside it, not under it.

- **Say what was checked.** Every report names the model it checked and states plainly that it
  checked the model, not the submitted drawing set (`prd.md` 5.7, I7). An office that models
  its geometry and drafts its documentation in 2D can submit sheets that diverge from what we
  measured, and I7 forbids letting "the model complies" be read as "the submission complies".
  A line of report copy, and the difference between decision support and an implied compliance
  claim. It now has to land in the generated file as well as the view, because the file is the
  thing that leaves the building.

- **The upload ceiling, measured.** High enough to serve 95% of users, and derived from peak
  worker memory rather than chosen as a round number — async removed the time constraint, not
  the memory one, and `acks_late` turns an oversized model into a poison message that starves
  every other tenant's queue. The measurement is the evidence; the number is then stated at
  upload time instead of discovered at failure time.

- **Invitations and roles in the UI.** The API has membership and roles; the frontend does not
  surface them yet. Last, and only if a first user needs a second seat.

**Out of the MVP, by decision, not by deferral:** the web overlay, marked sheets, and BCF
export. The first iteration reports and does not act; acting on findings arrives with the
agent layer and its permission levels (auto, edit, ask-first). This takes **gate 2 off the
MVP's critical path entirely** — it still decides what comes after the report, it no longer
decides what the report is.

### What has landed

**T-0024 — the browser evidence harness. Done 2026-09-02.** Phase 3 is almost entirely
frontend and `services/web` had no way to produce an evidence block: `make web-verify` is
eslint, tsc and vite build, none of which renders a component. Playwright now drives real
chromium against the `make up` stack — sign in, upload `door_width.ids`, upload
`three_doors.ifc`, run the check, open the report — and reproduces 1 PASS / 1 FAIL /
1 INDETERMINATE from the rendered page. `make e2e`, deliberately not part of `make verify`,
which stays fast and hermetic. Reasoning in `docs/decisions.md`; this is the instrument every
task below produces its evidence with.

**Found by running it, not by a test:** the requirement description reaches the screen as
`<ifctester.facet.Attribute object at 0x76f24ab599a0>` — `str(facet)` on a class with no
`__str__`, at `packages/engine/src/cadgpt_engine/check.py:77`. `ifctester` ships
`facet.to_string("requirement", spec, facet)` for exactly this and we were not calling it.
That is I5's resolvable basis rendering as a memory address, and it is the fourth defect this
repository has found by running the stack rather than by its suite. **T-0026**, sequenced
ahead of T-0025 — ranking a memory address by severity is not worth doing.

**T-0026 — the requirement a finding cites, in words. Done 2026-09-02.** `str(facet)` became
`facet.to_string(...)`, ifctester's own renderer, with the real `Specification` threaded
through. Reviewer-gated on I5, and the review earned its dispatch: threading the specification
activated an upstream early return that made a *prohibited* specification render "The
requirement is not applicable" directly under a FAIL verdict — a requirement line contradicting
the verdict beside it. Fixed in the same task by selecting `to_string`'s `applicability` clause
type for `maxOccurs == 0`, which is the branch upstream wrote for that case; a prohibited spec
now reads "The OverallWidth shall not be provided".

The review also caught the first round's test passing with its own fix reverted, and a false
paragraph in its evidence. Both corrected: there is now a real `door_prohibited.ids` fixture,
and the coordinator re-ran the mutation independently rather than accepting the claim — revert
the fix and `test_a_prohibited_specifications_requirement_line_never_contradicts_its_verdict`
fails on exactly the contradicting string. `ruff format` no longer scans `docs/**`, because it
was rewriting quoted defects inside task files into different code, and a task file's code
quote is evidence that must stay byte-identical to what it quotes.

**T-0025 — report presentation. Built 2026-09-02, review outstanding.** The report now leads
with coverage rather than trailing it, orders specifications and entity rows
FAIL → INDETERMINATE → PASS, and carries a Fail/Indeterminate filter with no PASS option —
passing entities are counted but never itemised by the engine, so a PASS filter would always
render empty and read as "no passes found". The filter cannot touch the summary: the counts
are counts of the run, not of the view, and the e2e spec asserts that unchecking Indeterminate
leaves its count at 1.

**Not done.** Its reviewer was dispatched and was still running when the coordinator session
ended, so the findings were lost. Re-dispatch before Phase 3 is marked complete — see
`docs/CHECKPOINT.md` and the task file, which records what the review was asked to hunt. The
short version: the filter is the dangerous surface and the e2e spec drives exactly one of its
states.

**T-0028 — a requirement that evaluated nothing must not report PASS. Done 2026-09-02.**
`_aggregate(failed, indeterminate)` became `_aggregate(passed, failed, indeterminate)`: a
requirement whose counts are all zero is now `INDETERMINATE`, not `PASS`. This is I7 pushed down
one level — `judge()` already refused to let a specification that checked nothing report a pass,
and the reasoning had never reached the requirement, which is the row the architect actually
reads. A prohibited specification's requirement now reads `INDETERMINATE | 0/0/0` under a
correctly `FAIL` specification, while `door_width.ids` is byte-identical and a new
`door_name_recorded.ids` fixture proves a requirement that genuinely evaluated three entities
still reports `PASS`. 166 tests, 5 contracts kept.

Reviewer-gated on the three-valued invariant, and the review earned it twice over. It proved the
dangerous direction — that no genuine PASS becomes an unknown — **by exhaustion rather than by
sampling**: `ifctester` writes `passed_entities` and `failures` only inside its
`for element in applicable_entities` loop, guarded by `if self.maxOccurs != 0`, and our
`classify()` never returns `PASS`, so a requirement reaches all-zero counts only when the
specification is prohibited or matched nothing. Both genuinely evaluated nothing; there is no
third way in. It then found the evidence block claiming the flipped status "renders through the
existing `StatusPill` component" — it renders nowhere. `requirement.status` is produced by the
engine, stored, serialised, typed at `types.ts:74`, and read by no component, test or spec. The
claim was corrected in place rather than deleted, and the gap became **T-0037**: until a status
pill sits beside the requirement description, this fix is real in the API and invisible in the
browser.

It also found the same class of defect still live one level up — `judge()` passes an *optional*
specification with **zero requirement facets**, which asserted nothing and checked nothing, and
the report calls it a PASS. Reachable from real user input; it validates against the
buildingSMART XSD. **T-0038.** Two decisions were settled and logged: a requirement that
evaluated nothing is *explained, never suppressed*, and a verdict-changing engine release *bumps
the engine version* so a stored run says which engine judged it.

### Queued

Re-ordered 2026-09-02 against the settled scope above. T-0027 and T-0028 were written before
the scope was settled and both survive it — they are defects in the report's honesty, and the
report is now the whole product.

- **T-0027** — the requirement as structured data the service localizes. T-0026 replaced an
  object address with upstream's English sentence, which made the gettext gap load-bearing:
  the line an architect reads first is now the one line that cannot be translated, against
  `presentation.py`'s stated design that the document holds codes and the service supplies
  wording. Carries two more I5 gaps with the same root — the bound renders as
  `{'minInclusive': '900'}` with no unit while the failing row reports a bare `800.0`, and the
  report never states what a rule applies to, because we drop the applicability facets
  ifctester does render. Now doubly load-bearing: the Markdown file inherits whatever this
  produces. Reviewer-gated.
- **T-0028** — a requirement that evaluated nothing reports `PASS`. `_aggregate(0, 0)` returns
  `PASS`, so a prohibited specification carries a green requirement over zero evaluations.
  `judge()` already applies this reasoning at the specification level and it was never pushed
  down to requirements — which is the row the architect actually reads. Pre-existing, found by
  the T-0026 reviewer. This is I7 inside the engine and it outranks new surface. Reviewer-gated.
- **T-0029** — say what was checked. The I7 disclosure copy, in the view and in the file.
- **T-0030** — the rule catalogue: a global `RulePack` beside the tenant-owned `RuleSet`, with
  jurisdiction, region, version and source citation, and a seeding path. No rule content.
- **T-0031** — rule selection at check time, recorded on the run so it stays reproducible.
- **T-0032** — the generated Markdown report and its URL on the job record.
- **T-0033** — the measured upload ceiling, and a resource-exceeded run that fails with a named
  reason instead of being redelivered forever.

## Phase 4 — Toward the PRD

The engine is the oracle everything else in `prd.md` depends on. The next structural pieces,
each of which the current architecture was shaped to receive:

- **The derivation layer** (`prd.md` 5.4) — ifcpatch recipes producing observations, so
  geometric rules become IDS bounds checks. It enters as a package beside the engine and is
  called before `run_check`. The observations it writes are the only queryable artifact
  there will be — the enriched model plus its relations, not a store standing beside it, and
  specifically not a graph database: topologicpy's dual graph and the `Related` observations
  already are the property graph.
- **Rule packs** (`prd.md` 5.5) — a pack is many IDS files plus clause records, not the
  single file `RuleSet` holds today. `RuleSet` was shaped to grow into it.
- **The coverage manifest** (`prd.md` 5.7) — which clauses were evaluated and which were not.
  It is the reporting half of the same three-valued discipline the engine already applies.
- **Findings as rows**, when dispositions arrive and findings need identity across runs.
  Until then the report is one JSON document, which is what it is used as.

---

## Constraints on what is not built yet

Added when `prd.md` was revised on 2026-09-02. They are recorded here rather than left in the
PRD because none of them is retrofittable — each decides the shape of a component before it
is written, and discovering it afterwards means writing the component twice.

- **The connector is a queue, not a thread pool.** Desktop CAD hosts run their API on the UI
  thread and crash or deadlock when it is called from anywhere else, while the connector's
  inbound channel is asynchronous by construction. Every host call is marshalled through the
  one idiom that host names, and long reads are chunked and cancellable: a read-only
  inspector that locks the host for two minutes is uninstalled before it finds anything
  (`prd.md` 5.10).
- **The agent's tool surface is closed and typed.** No evaluate-script tool, no pass-through
  to a host's macro engine, and a call that fails schema validation is rejected rather than
  coerced into something that will run. This is I2 at the transport: a model that cannot
  author geometry but can hand a script to the host authors geometry anyway (`prd.md` 5.9).
- **The assistance layer may not hold a model handle.** The data boundary is enforced the way
  I1 already is here, by an import contract rather than by policy, so the agent gets a
  contract of its own the day it lands. Pointing inference at an external endpoint is
  deployment configuration — never a per-request choice, never a default (`prd.md` 5.9).
- **Writes are named host transactions, and the check reports rather than reverts.** The
  rollback mechanism is the user's own undo stack with our move named in it. The findings
  delta is presented for them to decide on: a legitimate move can resolve a serious finding
  and raise a lesser one, and auto-reverting that hands the evaluator a veto over what may
  exist. Automatic revert is only for a write that failed or cannot be measured (`prd.md`
  5.11).
- **Repair never supplies geometry.** Where the write direction helps with a model missing
  its spaces, it may select the host's own room command and navigate to the place; it may
  never supply that command's geometric arguments, because computing the boundary is
  authoring the space no matter who clicks (`prd.md` 5.2, 5.11).

## Deliberately not built yet

PostgreSQL row-level security, WebSocket progress, S3 multipart upload authorization, a
transactional outbox, per-tenant rate limits, an admin UI, the agent layer, the connector.
Each is a real concern; none is on the path to the first user. They return when there is
something to protect or someone asking.

One item on that list is not deferred by choice: **the read-only pre-flight tool** is part of
PRD v0, not of a later phase (`prd.md` 5.2, 9), and this plan does not carry it yet. It waits
on gate 3, which is what says whether real models need it and what it would cost the designer.
It is also the first slice of the connector, so it inherits the queue constraint above from
its first day.

## The five questions this roadmap is still guessing at

`prd.md` 11 names five gates and says everything downstream of them is ordinary engineering.
None has been answered. Recorded here so the plan does not read as more certain than it is.

| Gate | Question | What it decides here |
|---|---|---|
| 1 | Ratification throughput, and how often an encoded bound disagrees with its source quote | Whether corpus coverage is a schedule at all, and the size of the confident-wrong-PASS risk |
| 2 | Do offices model, draft, or model then draft? | Whether Phase 3 leads with the overlay or with marked sheets, and whether the connector has a market |
| 3 | Do five real models from five offices derive, and what does pre-flight cost the designer? | Whether Phase 4's derivation layer meets models it can measure, and when pre-flight joins the plan |
| 4 | Can cadastral and zoning data be obtained and joined for a real parcel? | Whether two of the highest-frequency v0 checks exist at all |
| 5 | What does a first coverage manifest actually say in front of a real architect? | Whether an INDETERMINATE-dominated first run reads as honesty or as a broken tool |

Gates 1 and 2 are cheap, need no code, and are the two that would most change what gets built
next. Nothing in Phase 3 is blocked on them; most of Phase 4 is.
