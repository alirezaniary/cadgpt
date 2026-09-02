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

## Phase 3 — What the first real user needs — **NEXT**

Driven by use, not anticipation. In rough order of what a design office hits first:

- **Report presentation.** Findings grouped by severity, filtered by status, with the
  coverage statement above the findings rather than below them (`prd.md` 5.7). The current
  report view is honest but flat.
- **Say what was checked.** Every report names the model it checked and states plainly that
  it checked the model, not the submitted drawing set (`prd.md` 5.7). An office that models
  its geometry and drafts its documentation in 2D can submit sheets that diverge from what
  we measured, and I7 forbids letting "the model complies" be read as "the submission
  complies". This is a line of report copy and it is the difference between decision support
  and an implied compliance claim.
- **The web overlay.** A findings list is a document an architect skims; errors drawn on the
  model they just finished is something they act on. ThatOpen Engine or xeokit, both open
  source, both already load BCF viewpoints (`prd.md` 5.8).
- **Marked sheets.** Plan projection per storey with findings drawn on it, SVG and PDF, from
  `ifcopenshell.draw` (`prd.md` 5.8). Listed after the overlay on merit, but gate 2 can
  reorder it: in a market that models geometry and drafts its sheets, generated sheets are
  the submission artifact, and leading with them closes the model-to-sheet gap by
  construction rather than by disclosure.
- **BCF and PDF export**, through `ifctester`'s own reporters, with a fixture test of our own
  over the BCF output — that reporter has had open defects.
- **Large-model behaviour.** 47MB completes in ten seconds; the failure modes at 500MB are
  unmeasured. Upload directly to object storage rather than through the API process.
- **Invitations and roles in the UI.** The API has membership and roles; the frontend does
  not surface them yet.

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

## Regulation corpus workstream — **IN PROGRESS 2026-09-02**

This workstream supports Gate 1 and the later rule-pack phase without putting jurisdictional
logic into the checking engine. It converts the official INBR publications into a source-
anchored semantic corpus; compiling accepted semantics into buildingSMART IDS remains a later
and separate step.

1. **Corpus contract and inventory — DONE 2026-09-02.** Immutable hashes, MIME checks, canonical Persian and
   English titles, official ordering, editions, relationships, coverage, and quarantine.
2. **Page transcription.** Native positioned text where trustworthy; Persian/English OCR for
   scans, photographs, and watermarks; raw and normalized forms retained together.
3. **Document structure.** Ordered hierarchy, clauses, definitions, tables, figures,
   equations, symbols, units, printed page labels, and exact source spans.
4. **Model extraction.** Section-aware chunks capped near ten pages, two blind Luna
   extractions, strict Structured Outputs, and raw-response retention.
5. **Validation.** Deterministic anchor/reference/formula checks, independent Luna validation,
   official-web corroboration, conflict reconciliation, and quarantine.
6. **Publication.** Immutable JSON/JSONL plus a complete coverage and deferred-human-review
   report. Processing runs to terminal states without waiting for a reviewer; flagged content
   cannot enter the publishable corpus until reviewed later.

The active task is `docs/tasks/T-0024-regulation-corpus-contract.md`.

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
