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

**Reviewed and closed 2026-09-02**, on the third attempt to run that review — it was lost with
one session and pre-empted in another. It was worth recovering. The hunt list was right about
where the danger was, and wrong about which surface: the filter, which the review was written
to distrust, came back clean under reasoning about all four of its undriven states — nothing
renders as clean, empty or passing, a specification whose rows are all hidden still shows its
pill and matched count, the count band reads payload fields and never the filtered array, and
`bySeverity` is stable and correct over a shuffled seven-item input. The two defects were in
**coverage**, the thing the task existed to add.

**The coverage headline was a constant, not a measurement.**
`specifications_passed + specifications_failed + specifications_indeterminate` is identically
`specifications.length` for every report the engine can produce — `_specification` assigns
exactly one of three statuses to every specification and `_aggregate` has no fourth outcome —
so the sentence read "N of N" always. A run where 79 of 80 provisions matched nothing still
claimed eighty of eighty evaluated, directly above a block naming the ones that checked
nothing. That is `prd.md` §5.7's named failure — *coverage improves by narrowing applicability
while checking less* — shipped as the headline of the report.

**And `establishedNothing()` was naming a definite FAIL.** Its `matched === 0` disjunct
swallowed `NO_SUBJECTS_BUT_REQUIRED`: a required element that is *absent* is an established
violation, not an absence of evidence. The coverage block called it unevaluated while the
findings list below showed it with a red Fail pill.

Both fixed by making the two numbers come from one predicate — `evaluated` is now
`specifications.length - nothingEstablished.length`, and the predicate reads the reason code
`judge()` already assigned rather than re-deriving the engine's judgement in TypeScript, so the
frontend cannot silently diverge from it. A new `nothing_established.ids` fixture reaches the
branch with three specifications: one that passes, one optional that genuinely establishes
nothing, and one required over the same absent entity that is a real FAIL. The mutation was
re-run by the coordinator against the rebuilt container: the old numerator renders
"3 of 3 specifications in this rule set were evaluated" where the fix renders "2 of 3".

The review's remaining findings became **T-0034** (the filter banner states the filter's total
as 500 on a run with 3,623 findings, conflating what the filter hid with what the engine
capped), **T-0035** (one unknown status value makes the severity comparator non-transitive and
silently unsorts the whole list; a colliding React key on null-`global_id` rows) and **T-0036**
(RTL is claimed but never rendered under `fa` by any test, and `{spec.cardinality}` renders a
raw English payload value).

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

**T-0027 — the requirement as structured data the service localizes. Done 2026-09-02.**
The report's primary line read `The OverallWidth shall be {'minInclusive': '900'}` — a Python
dict repr, with no unit, beside a row reporting a bare `800.0`, in English written into the
stored document by the engine, and never saying what the rule applied to. The engine now names
the citation as data (`RequirementBasis`: facet type, subject, cardinality, and operator/value
comparisons) and the service supplies the sentence through `gettext`, exactly as
`reason_code`/`reason_label` already did. `description` stays as the fallback, so documents
stored before the bump still read. `REPORT_SCHEMA_VERSION` 1 → 2; nothing branches on it, and
the fallback keys off field presence rather than version, which is the more robust choice.

Verified by the coordinator inside the containers rather than from the evidence block: one
stored document renders `The OverallWidth shall be at least 900.` and
`OverallWidth باید دست‌کم 900 باشد.`, a hand-built v1 document still falls back in both locales,
and the browser now shows `All IFCDOOR data` above the requirement — a citation that finally
states its subject. No unit is invented: the IDS states none, so the sentence states none.

The review was gated on I5 and earned it. The mechanism was sound; two of the sentences it
produced were false. `xs:enumeration` is a **disjunction**, and the joiner was an unconditional
`" and "` — so a rule offering a choice of two values was reported as demanding both at once,
which no model can satisfy and no IDS ever asked for. And an operator the table did not
recognise fell through to a bare `"%(value)s"`, so `totalDigits` — "at most 4 significant
digits", and in `ifctester`'s own supported list — rendered as "shall be 4". That second one is
the more dangerous shape: `reasons.label_for` degrades to the *identifier*, visibly unresolved
and honest, while this degraded to a confident sentence indistinguishable from a correct one.
Both fixed, both re-verified on the real path in both languages, and both mutations re-run by
the coordinator: removing the enumeration grouping fails the test on `and` vs `or`, and
disabling the unknown-operator guard raises `KeyError: 'totalDigits'`.

The review also caught the evidence block reassuring the reader about exactly the case that was
broken, and dropped seven suspicions after executing them — format-string injection, XSS, unit
invention, lazy-string leakage, fa catalogue coverage, schema-version migration, and an
undisclosed deviation in the `to_string("applicability")` call that turned out to be *more*
correct than the task text. Remaining findings became **T-0039** (a restriction on the attribute
*name* leaves the subject null and puts the dict repr back; `applicability_description` is
still untranslated English in the stored document) and **T-0040** (`localize_report` raises
rather than degrading on a malformed `basis`, 500-ing the whole run detail).

**T-0029 — say what was checked. Done 2026-09-02.** `prd.md` §5.7's closing requirement, and
the cheapest I7 obligation in the product: the report now states, above coverage, that it
checked the model and not the drawing set the office submits, names the model by the filename
the architect uploaded, and names three concrete ways the two diverge — detailing drawn onto a
view, a schedule typed by hand, an area table in a titleblock. It closes: *"The result below
describes the model; it says nothing about the sheets."* Styled as a quiet rule rather than an
alert, because dressing a statement of scope as a warning teaches readers to dismiss it.

The review moved the copy rather than the words. The task had scoped itself to `services/web`
and so put the sentence in a TypeScript module and the frontend catalogues, with a comment
promising T-0032's Markdown generator would read the same source — **a promise that could not be
kept**, because T-0032 is server-side Python and a Celery worker can import neither. The
sentence would have been retyped into `django.po`, producing exactly the two-copy drift the
requirement existed to prevent, in exactly the copy that leaves the building. **The task file's
scope was wrong and the correction was the coordinator's, not the builder's.** The copy now
lives in `cadgpt.apps.review.disclosure`, rendered through `gettext` and served the way
`reason_label` already is; the view renders a string it was given. Settled as a general rule in
`docs/decisions.md`: *if a string will appear in the generated report file, it is authored on
the server* — the report has two renderers and only one of them is a browser.

Two smaller findings were folded into the same round rather than spawning a second pass over one
paragraph. The closing clause read "A **clean** result below describes the model", a
counterfactual printed above what is usually a FAIL report — and on a FAIL the live I7
misreading is the mirror one, the finding list read as *exhaustive* and implying compliance for
the unlisted remainder. One word dropped covers all three states. And nothing asserted the
wording: replacing the paragraph with the literal `"{{filename}}"` left every assertion passing.
Verified closed by the coordinator — gutting the copy now fails with
`Received string: "What this report checkedthree_doors.ifc"`.

Queued as **T-0041**: a verdict is reachable without its scope. The reviews list renders
"Complete · Fail · 1 / 1 / 1" before anyone opens the report, and that row is the surface a
reader most plausibly screenshots into an email.

**T-0030 — the rule catalogue. Done 2026-09-03.** A global `RulePack`
beside the tenant-owned `RuleSet` — jurisdiction, region, version and a required source
citation — with a read-only filterable API and an idempotent `seed_rule_packs` command. No rule
content: seeded under `jurisdiction="sample"` from the repository's own fixtures, because the
product owner authors the real packs in a separate thread and inventing a jurisdiction would be
inventing a rule.

The hard part was the invariant it does not fit. A shipped pack belongs to no tenant, so the
catalogue needs a viewset that is deliberately *not* tenant-scoped — which is precisely what the
structural test exists to fail. The answer holds: `GLOBAL_CATALOGUE_VIEWSETS` is a **declaration,
not a skip list**. The original test never consults it and gained no new escape hatch; a second
test asserts the declaration stays true, failing the moment a model named there acquires a
`tenant` column. Verified by mutation — making `RulePack` tenant-owned fails four tests,
including the *pre-existing* structural one, which is what proves no hole was opened. The
guarantee is narrower after this task than before it, not wider.

**Reviewed, and the first review this session to find nothing to fix.** It re-registered two
tenants of its own rather than trusting the evidence, re-ran the two-tenant and refusal
assertions from scratch, and tested writes the evidence had not (`PUT`, detail `POST`) — 405 on
all. The write refusal is by construction: the viewset mixes in only list and retrieve, so the
write handlers do not exist. `source_citation` is genuinely enforced against empty and
whitespace-only input, and the seeded citation is real attribution naming the fixture path and
stating it is not regulation.

Its findings are all about the surfaces *around* the catalogue rather than the invariant it was
gated on, and are queued as **T-0042** (the serializer hands out a storage URL that `curl`
fetches with no Authorization header, and which in production advertises a download that returns
the SPA's HTML), **T-0043** (the seeder's idempotence is an unlocked pre-check that TOCTOUs
across processes into an unhandled `IntegrityError` and an orphaned file) and **T-0044** (the
seed manifest is hardcoded Python, so the first real pack requires an image rebuild).

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

Added 2026-09-02 from the T-0025 and T-0028 reviews. They sit behind the MVP tasks above —
none blocks the report shipping, and the two that touch honesty directly (T-0037, T-0038) are
the first of them:

- **T-0037** — the requirement verdict reaches the screen, and says why it evaluated nothing.
  `requirement.status` is produced, stored, serialised, typed and read by nobody, so T-0028's
  fix is invisible in the browser. Carries the reason down so a row that evaluated nothing
  explains itself. Wire format change; `REPORT_SCHEMA_VERSION` bump.
- **T-0038** — a specification that asserted nothing must not report PASS either. `judge()`
  passes an *optional* specification with zero requirement facets. Same I7 failure as T-0028,
  one level up. First application of the engine-version bump decision.
- **T-0034** — the filter banner must not claim credit for what the engine capped.
- **T-0035** — two latent report-view defects: an unsortable list and a colliding key.
- **T-0036** — the Persian report: prove RTL, and stop rendering a raw payload value.
- **T-0039** — the subject of a citation: structured in the engine, worded in the service.
- **T-0040** — `localize_report` must degrade, not 500.
- **T-0041** — a verdict is reachable without the statement of what was checked.
- **T-0042** — the catalogue hands out a storage URL nothing authenticates.
- **T-0043** — the seeder must survive a race and speak the application's error language.
- **T-0044** — seeding real packs: a manifest, and knowing when the catalogue diverges from disk.

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
