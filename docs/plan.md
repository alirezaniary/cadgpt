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

**All three clauses of the MVP sentence now exist in code as of 2026-09-03** — upload (T-0024 and
before), selection (T-0031), and the report file (T-0032). **Phase 3 is deliberately not marked
done.** T-0033 remains unbuilt, and two findings from T-0032's review bear directly on whether the
sentence is true in practice rather than in principle: a report could silently never be generated with
no way to ask for it again — **closed by T-0051** — and the download button a real user would press
has never been executed by any test (T-0053). T-0051's review then found the same lost-dispatch
hazard still open upstream, where it strands the check itself (T-0056). The clauses are implemented; that they hold for a real user is not
yet established, and this plan does not record it as though it were.

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

**T-0031 — rule selection on the run. Done 2026-09-03.** The MVP's middle clause: a review can
now be created with no uploaded rule set and checked against packs picked from the catalogue,
`POST /reviews/{uuid}/check/` with `rule_packs: [uuid...]`. The deliberate choice the task
demanded be made explicitly is **one run with several rule sources**, not several runs —
`_evaluate_selection` calls the engine's unchanged `run_check` once per pack and `_combine_reports`
concatenates the specifications, so the coverage sentence counts across the whole selection instead
of resetting per pack. `ReportView`'s `evaluated` computation needed no change to inherit that: it
already sums over `report.specifications`, and a combined report simply hands it more of them.
Unknown and duplicate packs are refused with named reasons — silently running fewer rules than
asked for is the coverage failure this product exists to refuse.

The selection is stored as **data, not a foreign key**: `CheckRun.rule_pack_selection` holds each
pack's uuid, name, jurisdiction, region, version and a SHA-256 of its bytes, captured at dispatch
before the run row exists. Found by running it rather than by the suite, for the fifth time in this
repository: making `Review.rule_set` nullable turned `_claim`'s `select_for_update()` into a lock
across a LEFT OUTER JOIN, which sqlite does not enforce and Postgres does — green suite, and the
first real check against the compose stack raised `NotSupportedError`. Fixed with
`select_for_update(of=("self",))`; the unguarded *class* of defect became **T-0050**.

**Reviewed, and the review found the recording hollow while the intricate surfaces held.** Tenancy,
the narrowed lock and the three-valued combination were all attacked and all cleared — the lock is
the only `select_for_update` in the codebase, so nothing relied on the incidental locks it dropped,
and `_status_from_counts` is line-for-line identical to the engine's `_aggregate`. The defect was
that `checksum_sha256` was **written by one function and read by nobody**. Swap the bytes behind a
cited uuid between dispatch and execution and the run succeeded, flipped `FAIL` to `PASS`, and
stored a citation naming a pack and hash it had not checked. Not exploitable through the product as
it stands — no path mutates a seeded pack's bytes — but the guarantee rested on a docstring while
the column that could enforce it sat inert, and `docs/decisions.md` had already written down the
condition under which the checksum would become "the only thing still telling the truth about what
a run checked". Now verified at execution, refused as `CheckRunFailure.RULE_PACK_MODIFIED`.

Two evidence items claimed proof they could not deliver, which is the half worth carrying forward.
The worker log line was built from the citation, so it could only ever agree with the citation —
the selection JSON echoed back and pasted as proof the check ran against those rules. And the
reproducibility test mutated the catalogue by seeding a **new row**, which a plain `ForeignKey`
passes identically; the only edit that distinguishes a snapshot from an FK is
same-uuid-different-bytes, the exact case nothing tested. Both fixed, and the mutation re-run by
the coordinator: disabling the checksum comparison fails the new test while the corrected log line
prints `cited_name: "Accessible door width"` beside `evaluated_ids_title: "Door name recorded"` over
an outcome of `PASS`. 208 tests, 5 contracts kept.

Its remaining findings are all in the surfaces around the selection and are queued as **T-0045**
(the picker fetches one 20-row page and filters it client-side, so a pack on page 2 reads as "no
packs match this filter" — and the near-term plan is Iranian, then EU, then US), **T-0046**
(`services/web` has no test runner at all despite `CLAUDE.md` calling it RTL-native; the picker has
never been rendered and two defects wait in it), **T-0047** (`base/files.py` typed `Any` at a new
shared boundary), **T-0048** (a failed run shows the tenant `list index out of range` and internal
storage keys, and never shows what it was supposed to check), **T-0049** (no finding carries the
pack identity that produced it, which `prd.md` §5.7 requires and which is what would make
`source_citation` reachable at all) and **T-0050** (the sqlite test backend cannot see the
Postgres-only defect class this task itself hit).

**T-0032 — the report as a file. Done 2026-09-03.** The MVP's last clause. A Markdown generator
that is not a sibling design but the report already built and reviewed, rendered for the form that
leaves the building: `ReportView.tsx` is the specification and the file follows it — the disclosure
first, coverage before findings, FAIL → INDETERMINATE → PASS, a coverage numerator that is a real
measurement, specifications that established nothing named rather than counted, all three counts
always. It reads `localize_report`'s output, so wording and rendering stay one path. Generation is
dispatched on commit from `_succeed`, idempotent under a row lock, stored through `media` under the
tenant's prefix and served by an authenticated route — deliberately not the raw storage URL that is
already queued as T-0042. Correct for both kinds of run T-0031 left behind: an uploaded `RuleSet`
or a catalogue selection, with coverage spanning the whole selection.

**The language decision, made deliberately and logged:** the file renders in `Tenant.language`,
activated once at generation. Markdown carries no `Accept-Language` and the file is written once, so
there is no request to negotiate from. If the tenant's language later changes the stored file does
not — it is bytes in storage, exactly like an uploaded model.

**Reviewed, and the review found a false compliance claim reachable from a rule file.** Author-
controlled text reached the file unescaped everywhere outside table cells, so a specification named
`Doors\n\n## Coverage\n\n99 of 99 specifications were evaluated.\n\nEverything complies.`
rendered a **second coverage section asserting compliance nobody established**, in the one artifact
a client reads. The React view is structurally immune because it escapes text nodes; this was a
file-only regression against the specification. Closed, and proven on the real stack by building an
IDS that carries the injection and running it end to end.

Two more fix-now findings, both the now-familiar shape. The on-commit wiring test **recorded zero
calls to the code it tested** — `execute=False` drains nothing, so the check never ran and the
assertions passed on emptiness; replacing `on_commit` with a bare inline `.delay()` passed the test
and the entire suite, while the evidence offered only a quotation of the line. Replaced with a test
that fails on exactly that mutation. And the Persian *file* had already drifted from the Persian
*screen*, renaming the three-valued verdicts — `رد` against `مردود`, `نامعلوم` against `نامشخص` —
in the first release that had two renderers, with the evidence pasting the file as proof the
translation worked. Reconciled word-for-word. 228 tests, 5 contracts kept.

What the review cleared is worth recording too, because it was cleared by execution rather than
reading: I7 is genuinely inherited from `disclosure.py` rather than retyped, `N of N` and T-0025's
`establishedNothing` defect are both unreachable, tenancy holds with no serializer leaking a storage
URL, and the language decision does what it says.

**T-0051 — a report that was never generated can be recovered. Done 2026-09-03.** T-0032 shipped a
generator dispatched on commit from `_succeed`; nothing recovered a dispatch that was lost. A run
could report `succeeded` and never produce its file, permanently — `execute()` returns early for any
terminal run, `reap_stalled` only touches `RUNNING`, and every run predating T-0032 was in exactly
that state. Now: an authenticated `POST` on the same URL as the download, a `backfill_report_files`
command, and a `missing_report` queryset. The backfill recovered 70 real rows in the dev database.

**The deliberate decision, in `docs/decisions.md`:** a rendered report that exceeds the storage cap
does **not** retro-fail the run. The check ran to completion and its counts are real; failing it
because the Markdown did not fit would tell the user their check did not happen. The failure is
recorded on the run instead, so "generation failed terminally" is distinguishable from "not
generated yet" — and the cost is recorded too, that such a run is then excluded from `missing_report`
until something deliberately sweeps it (T-0059).

**Reviewed.** The core held under enumeration rather than sampling: every way generation can fail —
`.delay()` raising, the worker lost between COMMIT and callback, `generate` raising outside the
retried exceptions, storage errors, a crash after the Media row is written — leaves a state
`missing_report` finds. Concurrency was proven on **real Postgres**, three concurrent `generate()`
processes yielding one file, because the sqlite test backend ignores the row lock entirely and any
sqlite-based race proof would have been worthless. No combination of file/error ever advertises a
report that does not exist.

Two fix-now findings. Three shipped docstrings cited `docs/decisions.md` for a decision **the file
did not contain** — the reasoning lived only in the task file, which is not the decision log; now
appended. And the new Playwright spec **passed with the recovery button inert**: its route glob
missed the POST entirely, and because the page polls every 2s while the report is pending, the
second body arrived whether or not the button did anything. Removing the `post` route from the
router would have left it green. This was the fourth consecutive review to find evidence that could
not have failed, and the first where the evidence claimed a mutation proof by name. Rewritten to
gate on a real 2xx from a disjoint interception, and killed and revived by the reviewer's own
mutation. 233 tests, 5 contracts kept.

**The review's most consequential finding is not in this task.** The identical lost-dispatch hazard
is still open on `request_check`'s dispatch of `execute_check_run`, and there it is worse: the run
sits `PENDING` forever, nothing reaps PENDING by design, this task's recovery POST returns 409 for a
non-succeeded run, and `MAX_IN_FLIGHT_RUNS = 1` means the dead row blocks the review from ever being
checked again. Executed against the live stack. **T-0056.**

**T-0033 — the measured upload ceiling, and the poison message. Done 2026-09-03.**
`MAX_UPLOAD_BYTES` was `512 * 1024 * 1024` — a round number nobody derived. It is now
`126 * 1024 * 1024`, and the derivation is written beside the constant with its denominator: the
worker's now-*declared* `mem_limit: 4g` at `--concurrency 2`, less the Celery parent, less an
allocator/GC factor, against measured peak RSS. The number moves if the concurrency or the container
limit moves, and says so.

**The half that mattered more was the queue.** `acks_late` plus `_claim`'s deliberate re-claim of a
`RUNNING` run — correct for a worker killed by a deploy — made an OOM-killed model a poison message:
redelivered, claimed, killed, forever, on a queue shared by every tenant. `CheckRun.claim_count`
bounds it, incremented **inside the same row-locked write that flips the run to `RUNNING`**, which is
the one placement an OOM kill between claiming and finishing cannot lose. The run ends as
`RESOURCE_EXHAUSTED` — a failed run with no report and no counts, never an `INDETERMINATE` result and
never a finding about the model.

**Reviewed, and the review's headline was that the task had reintroduced what it existed to
eliminate.** The derivation reached 126MB and the first round rounded it to 100MB "for margin and
memorability" — choosing a round number, which the standing decision forbids by name, discarding
21MB of measured headroom. Corrected. The decision's other half — *high enough to serve 95% of
users* — turned out to be entirely unaddressed behind a `NOT DONE — Nothing`, resting on one 47MB
sample; it cannot be established without a model corpus we do not have, and it is now recorded as
explicit **NOT DONE** rather than silently claimed.

Two evidence items could not have failed. A pasted generation command omitted the script's required
`--output` and would have exited at argparse; and the poison-message proof queued its second run
**25 seconds after the cycle had already stopped**, which demonstrates the worker still functions,
not that the queue was ever unblocked. Redone at `--concurrency 2` with both runs 0.5s apart: the
small run is claimed on a second fork and succeeds in 0.43s while the poison run's first attempt is
still alive. Finally, the one user-facing string the task added was a raw English f-string that
`ReviewsPage` renders verbatim, so a Persian tenant would have read English internals while the
Persian translation added in the same diff sat unreachable — now through `gettext`, with the
unproven "most likely the memory limit" claim dropped. 235 tests, 5 contracts kept.

**T-0067 — a way in, and a first workspace. Done 2026-09-04.** Found by using the product, not by
a task in the queue: the frontend had a sign-in form and nothing else — no registration screen and
no link to one, so a person with no account and no invitation could not start using the product at
all. `report.spec.ts` said as much in its own comments — account and tenant creation were seeded
through the API "because the SPA has no screen for either." Registering alone would not have fixed
it either: a freshly registered user has zero tenants, and the workspace `<select>` just rendered
an empty "No workspace yet" with nothing to click. Product owner confirmed both belong in one task.
`RegisterPage` reuses `useSession().signIn` rather than teaching `session.tsx` a second way to
plant a token; `CreateWorkspacePage` derives a collision-resistant slug client-side rather than
asking a brand-new user for a second field, justified against `Tenant.slug`'s uniqueness constraint
in the evidence.

**Reviewed, gated on the tenancy invariant, and two of four findings were fix-now — one of them a
real tenant-isolation leak this task introduced the path to.** `session.tsx`'s `signOut` cleared
the user, tenant and access token but never the TanStack Query cache; query keys are not
user-scoped, so the next person to sign in on the same tab rendered off the previous user's cached
tenant name and rule sets — live-reproduced by the reviewer. It also broke this task's own
acceptance criterion: a stale cache meant `CreateWorkspacePage` never rendered for the new user at
all. Fixed with `queryClient.clear()` on sign-out. The second finding falsified the evidence block
itself: the "no more empty dropdown" guard fell through to the shell while the tenant list was
still loading, flashing the exact broken state the task existed to remove — the first-round
Playwright assertion had auto-retried past the window rather than proving it absent. Fixed with an
explicit loading state, and the fix uncovered its own test bug in the process: the original
`toHaveCount(0)` check auto-retried past the same window it was meant to catch and passed against
both the broken and fixed code; rewritten as a non-retrying point-in-time sample, then proven to
fail against the reverted code before being restored. Both fixes are mutation-tested — reverted,
shown to fail for the stated reason, restored, shown green — against a freshly rebuilt container,
not a cached bundle. Two smaller findings queued rather than fixed here: **T-0068** (registration's
failure path never explains why — a 12-character password minimum enforced but never stated, and a
throttled second call can strand a created-but-unconfirmed account with no recovery messaging), and
**T-0069** (three onboarding edges: a revoked last membership has no way back to the workspace
screen without a reload, `slugify` collapses every non-Latin name to one shared stem, and
`RegisterPage` never sends `language` so a Persian-UI signup still gets an English-language
account).

**T-0070 — a design framework, RTL-Persian-first, in place of bare HTML. Done 2026-09-04.**
Requested directly by the product owner after seeing T-0067's new screens: `styles.css` was two
structural classes and raw browser defaults on every input, select and file picker — that
predated T-0067, which correctly matched the existing bare style rather than prettifying two
screens in isolation. Settled in conversation: RTL Persian is the primary, native design
target now — not an LTR design mirrored for RTL — with no change to dual-language support or
`docs/decisions.md`'s multinational-tenant stance.

Researched `https://zohal.io/` for real before writing any CSS — a Farsi-native fintech product
built `dir="rtl"` from the ground up, not translated. Its characteristics, not its values,
moved into this app's tokens: a deep navy-indigo accent scale in place of a flat blue, a
generously rounded `rounded-xl`-equivalent radius in place of a flat 8px, a 4px-based spacing
rhythm, a small real type scale, and — the most directly reusable finding — a self-hosted
Persian webfont rather than a bare `font-family` hoping a system has it installed. That last
one was a real, pre-existing bug: Vazirmatn was named in `:lang(fa) body` and served by nothing,
silently falling back to Tahoma on almost every machine. Now vendored as two `woff2` subsets and
confirmed loading with `200 font/woff2` over HTTP from the running container.

Every scattered magic number in `styles.css` — font sizes, radii, weights — now reads from the
new token layer; `--pass`/`--fail`/`--indeterminate` and the dark-mode block's existing lines
are untouched, confirmed by an empty `git diff` on those specific lines. `<select>` deliberately
keeps its native arrow rather than a custom one — a dropdown arrow's position flips physically
between `rtl` and `ltr`, and the platform already gets this right for free, the same
"inherit before writing" call this codebase makes everywhere else. `ReviewsPage` and the report
view needed zero code changes — both already used the class names the new primitives target,
so the whole visual pass on the two busiest screens is the primitives layer alone.

Proven with twelve real screenshots — fa/RTL first as the primary target, en/LTR second
confirming a clean mirror — through the actual sign-in → register → create-workspace →
upload → check → report path, reaching a real 1 pass / 1 fail / 1 indeterminate report in both
languages from a cold start. The existing six-spec e2e suite passes unmodified in behavior; the
one spec asserting on `.pill`'s exact text confirms the new status-dot `::before` doesn't leak
into `textContent`. Two items named NOT DONE rather than silently skipped: the native `<select>`
arrow (a deliberate call, not a gap) and the file input's "Choose File" label, which stays in
the browser's own UI language regardless of page language — a platform limitation, not something
CSS can address.

**T-0071 — T-0070 measured zohal.io's real colors and assigned them the wrong roles. Done
2026-09-04.** The product owner rejected T-0070's result on sight: light background, a muted
navy button — nothing like the reference. Correct. T-0070's evidence had the right raw numbers
but backwards roles — it read the *darkest* navy in zohal's scale as a small accent to place on
a white page, when that navy **is** the page background, unconditionally, with no light variant
at all, and the warm orange it called "sparing" is the primary call-to-action color. Right
ingredients, inverted recipe — a failure of verification, not of research: nobody had looked at
the two results side by side before calling T-0070 done.

Re-measured directly against the live site with `getComputedStyle` this time, not by reading
markup for hex values — sampled at six points down the full page (`rgb(38, 41, 63)`
unconditionally) and the actual signup button's rendered color, not a guess from a class name.
`:root` now carries that identity directly: dark navy background and card layer, orange accent
with dark text on its fill (matching how zohal itself sets it), and the old
`prefers-color-scheme: dark` media block is gone — not merged, removed — because the default
*is* the dark identity now, the same way the reference has no light variant to opt into. Also
fixed in the same pass, raised separately: the topbar's native `<select>` elements were raw
OS-chrome dropdowns clashing with any theme underneath them — `appearance: none` with a redrawn
chevron, positioned with `right`/`left` and flipped under an explicit `[dir="rtl"]` override,
the one place in the file a direction branch is correct because `background-position` has no
logical-property equivalent.

Verified directly against a live `zohal.io` screenshot taken in the same session, not by
argument — the coordinator did not delegate this correction to a fresh agent a third time.
`make web-verify` clean; full e2e suite passes at `--workers=1` (flaked twice under the default
4 parallel workers on two different assertions in the same long spec, reproduced and diagnosed
as pre-existing Postgres/Celery contention before trusting it, not waved off — nothing in a
CSS-only diff touches timing or backend state).

**T-0072 — an avatar menu in place of two selects. Done 2026-09-04.** The product owner
rejected the topbar's styled `<select>` outright — "no ugly dropdown" — and settled two
things in the same conversation: the account menu becomes an avatar-triggered popover
(tenant name, email, workspace switch, sign-out), and the product is single-language,
hardcoded to Persian, not user-switchable. Recorded in full in the task file; not yet
committed as of this plan update.

**T-0073 — a project to hold reviews. Done 2026-09-04.** The missing tenant-owned layer
between the tenant and `Review`: `cadgpt.apps.project`, a three-step migration
(`Review.project` added nullable, backfilled to one `"عمومی"` project per tenant with
existing reviews, then made non-nullable), and the API — `ProjectViewSet` and a `project`
filter on `ReviewFilterSet`. Migrated the live dev database cleanly (171 reviews, 118
tenants). Reviewer-gated on the tenancy and import-contract invariants it touches;
verdict was clean — no invariant violated, evidence held up under independent
re-verification — with four findings queued rather than fixed in place: **T-0075** (a
`review_count` that counts soft-deleted reviews, and a project that can never be deleted
once any review has ever existed under it — `PROTECT` fires permanently with no release
path), **T-0076** (the new app shipped with no test package; the structural isolation
test only checks the class hierarchy, not that `get_queryset` actually stayed
tenant-scoped — swapping in `Project.objects.all()` passes the whole suite today),
**T-0077** (`ReviewSerializer` never exposes the `project` a review is now required to
belong to). T-0074, below, is not a new finding — the frontend's only review-creation
call not yet sending `project` is exactly what T-0074 exists to close.

**T-0074 — a changelist, an add form, and a detail view, in place of one page. Done
2026-09-04.** The frontend half of the same rejection: the product owner wants Django
admin's shape, minus the visual style — a changelist, a separate add form, a separate
detail view, three levels deep, **workspace → projects → reviews**, a review's detail
page carrying its own runs and report. Wired up `@tanstack/react-router` (a declared,
unused dependency since before this session) into `/projects`, `/projects/new`,
`/projects/:uuid`, `/projects/:uuid/reviews/new`, and `/projects/:uuid/reviews/:uuid`
against T-0073's API, and removed the user-facing rule-set upload card entirely per
`docs/decisions.md`'s 2026-09-04 entry — UI removal only, backend `RuleSet` untouched.
Not review-gated (touches no invariant). Full e2e suite (6/6) green against the rebuilt
stack, reproduced twice; running the real stack — not the diff — caught and fixed two
genuine bugs: sign-out/workspace-switch left a stale tenant-scoped URL in the router,
404ing the next session's landing page, and the review-detail "busy" state lagged an
already-succeeded run because it read a slower-polling query than the one that was
actually current. One item flagged NOT DONE rather than fixed unilaterally: the
`nothing_established.ids` coverage-math scenario lost its e2e path now that arbitrary IDS
upload is gone from the UI and no catalogue-seeded pack reproduces it — queued as
**T-0078** (a backend seed-manifest change, outside this frontend-only task's scope).

**T-0056 — a lost check dispatch kills the review, not just the file. Done 2026-09-08.**
The MVP's highest-severity standing gap: `ReviewService.request_check` refused every future
check permanently — `MAX_IN_FLIGHT_RUNS = 1` counting a dead row forever — if a `PENDING`
run's `on_commit` dispatch was ever lost (process killed between `COMMIT` and the callback,
or `.delay()` itself raising). `_reap_lost_dispatch` closes it: called only from inside
`request_check`, only at the instant it is about to refuse, it fails a `PENDING` run with no
`task_id` older than `CHECK_RUN_STALL_SECONDS` (reusing `stalled()`'s existing constant, not
inventing one) so the request below can proceed. Re-dispatch instead of failing was
considered and rejected: a second, independently-issued `.delay()` for a run whose original
dispatch actually reached the broker would race a genuine claim, risking a model evaluated
twice at once.

**Reviewer-gated, and the review earned its dispatch twice over.** First finding: the
initial implementation selected the lost rows into Python objects and wrote each back with a
per-row `.save()` — exactly the TOCTOU race the design rationale rejects re-dispatch to
avoid, reopened by the implementation. A worker's `_claim` flipping a row to `RUNNING`
between the read and the write would have that row overwritten back to `FAILED`
mid-evaluation. Fixed by collapsing selection and write into one filtered `UPDATE`
(`runs.dispatch_lost(...).update(...)`), mirroring `reap_stalled`'s own pattern — Postgres
re-evaluates the `WHERE` clause against the row's current state at the moment of the write.
Second finding: the evidence's live-stack paste for the recovery step named a run the
reviewer found had **zero rows in Postgres** and a `NotFoundError` in the worker log — the
first pass's cleanup script had deleted it before independently confirming it existed, and
guessed at an explanation instead of checking. Re-run cleanly, with an explicit post-hoc
existence check, before this entry was written. A third finding — the age threshold itself
was unpinned by any test, and removing it left the whole suite green — closed with a new
test, mutation-verified by hand against the reverted clause.

Two findings queued rather than fixed here, one of them now the single most urgent item in
the backlog: **T-0084** (`reap_stalled_runs`, the RUNNING-side sibling of this fix, is wired
into no Celery beat schedule anywhere and has never executed in any deployment — the same "a
review can be stuck forever" failure this task closed for PENDING is still fully open for
RUNNING) and **T-0085** (the reactive-only trigger leaves a lost-dispatch run
indistinguishable from a healthy one for up to 30 minutes). A fourth finding — the server
never activates the Persian the product was decided to be hardcoded to, so this task's own
new failure text renders in English absent an explicit `Accept-Language: fa` — is real,
verified pre-existing, and out of scope; queued as **T-0083**.

**T-0084 — `reap_stalled_runs` is registered nowhere and has never run in production. Done
2026-09-08.** The RUNNING-side sibling of T-0056's fix: `CheckRunExecutor.reap_stalled()` was
correct but had no caller anywhere — no `CELERY_BEAT_SCHEDULE`, no `beat` service, no
management command — so a `CheckRun` whose worker died mid-evaluation sat `RUNNING` forever
and, under `MAX_IN_FLIGHT_RUNS = 1`, blocked its review permanently, in every deployment,
since the task was written. Closed with a `CELERY_BEAT_SCHEDULE` entry ticking at
`CHECK_RUN_STALL_SECONDS / 4` and a `beat` service in `deploy/compose.yaml`, both logged in
`docs/decisions.md` alongside the scheduler choice (Celery's built-in file-backed
`PersistentScheduler`, sufficient because `reap_stalled`'s `status=RUNNING` filter is already
idempotent under at-least-once ticking — proven live, not assumed).

**Reviewer-gated, and the review re-derived the real path independently rather than trusting
the builder's paste.** It reproduced the DB rows and worker logs from the running stack down
to the microsecond, disproved two hazards it went looking for on its own (queue routing
sending the reap task behind CPU-bound checks; `acks_late` redelivery resurrecting an
already-reaped row), and caught one gap the builder's own evidence hadn't closed — a live tick
at the real, unoverridden 1800s default, not just the accelerated 60s override used for
observability. One finding fixed rather than queued: nothing in `make verify` tied
`CELERY_BEAT_SCHEDULE`'s task-name string to the registered task, so a rename or typo on
either side would silently reopen the exact "review stuck forever" failure this task closed,
with a green suite. Closed with `services/api/cadgpt/tests/test_celery_beat_schedule.py`,
mutation-verified against a deliberately broken task name; the first version of that test was
itself order-dependent on Celery's lazy task discovery and was corrected to call
`app.loader.import_default_modules()`, the same call a real worker's bootstep makes, before
being trusted.

**T-0085 — a lost-dispatch run is invisible and the review looks falsely blocked for up to 30
minutes. Done 2026-09-09.** T-0056's `_reap_lost_dispatch` only ever ran reactively, from
inside `request_check`, at the instant it was about to refuse a new check — a run whose
dispatch was genuinely lost, in a review nobody happened to retry, rendered as an ordinary
`pending` run for up to `CHECK_RUN_STALL_SECONDS` (30 minutes at the default), with no better
signal than before T-0056 landed at all. Closed by giving Beat's tick (T-0084) a second task,
`review.tasks.reap_lost_dispatch_runs`, calling a new `CheckRunExecutor.reap_lost_dispatch()`
— a second caller of the exact same atomic UPDATE `_reap_lost_dispatch` already used
(`CheckRunQuerySet.dispatch_lost`, byte-for-byte unchanged), on the same
`CHECK_RUN_STALL_SECONDS / 4` cadence T-0084 already established. The blind window is now
bounded to ≤450s at the production default, down from unbounded. Deliberately no frontend
rendering change — the task's own scope treated the periodic sweep as sufficient on its own,
and a `PENDING` run within that bound is a genuinely bounded delay, not a false signal. Both
decisions (proactive sweep, no frontend change, with its reopen condition) logged in
`docs/decisions.md`.

Not reviewer-gated, so the coordinator audited it directly: independently re-ran `make verify`
(242 passed, 5/5 contracts), read every diff, and confirmed the cross-tenant test's fixtures
were real rather than assumed. One thing fixed: `_reap_lost_dispatch`'s own docstring still
said "never as a periodic sweep — that restraint is what keeps this safe," which this task's
own change made false — a future reader would have believed caller-count was the safety
property instead of the UPDATE's `WHERE` clause. Reworded, along with `request_check`'s
docstring, to name both the reactive and proactive halves of the recovery; `make verify`
re-run clean after.

**T-0083 — the hardcoded-Persian product never activates Persian on the server. Done
2026-09-09.** The frontend was settled single-language, hardcoded Persian since T-0072; the
server never got the equivalent decision — `LANGUAGE_CODE = "en"`, and most affected text
(report prose, `CheckRun.failure_detail`) is written by the Celery worker, which has no
HTTP request and thus no `Accept-Language` for `LocaleMiddleware` to ever read. Closed with
two layers: `LANGUAGE_CODE` flipped to `"fa"` (the fallback every unactivated thread and
every real header-less request from `services/web` resolves against), and
`cadgpt.apps.base.tasks.BaseTask.__call__` — the one method every Celery task runs through
— now explicitly wraps every task body in `translation.override(settings.LANGUAGE_CODE)`,
so the worker's language does not depend on `gettext`'s own fallback alone.

Found and fixed two real pre-existing violations of CLAUDE.md's "every user-facing string
goes through gettext" while auditing every `failure_detail` write site: `reap_stalled`
(T-0084) wrote a bare Python string literal, translatable by nothing; four DRF permission
classes in `tenancy/permissions.py` did the same (fixed with `gettext_lazy`, not eager
`gettext` — they're class attributes evaluated at import time, before any language is
known). Also closed a real, silent testing gap: the `.po` catalogue had never once been
compiled to `.mo` in any test run, including CI, so 22 tests were asserting translated
output against an accidental English fallback the whole time — `make verify`/CI now compile
messages before `pytest` runs, and each affected test now either states an explicit English
override (for tests whose real subject is structure, not wording) or asserts the real
Persian a header-less request now genuinely returns.

Not reviewer-gated; coordinator-audited instead — independently re-ran `make verify` (245
passed, 5/5 contracts) and read every diff. No fix-now findings: the new regression tests go
through the real Celery dispatch path, assert against catalogue-derived expected strings
rather than hand-typed ones, and guard against silently matching two English fallbacks
against each other. Two minor pre-existing items named in the evidence but left as notes
rather than spawning further tasks: `make schema`'s output now mixes languages (affects
nothing in `verify`/CI, nothing committed depends on it), and `report_generation.py`'s
docstring describes a per-member language override that was never actually wired into any
request path.

**Milestone review, 2026-09-09 — T-0056+T-0084+T-0085+T-0083 as a combined diff.** All four
are done; together they close "a review can be permanently stuck forever" for both PENDING
and RUNNING, and the server-side language gap. `/adversarial-review`'d as one unit, since
individual per-task review each looked at one commit at a time. One real finding, reproduced
before being trusted: `test_celery_beat_schedule.py` (T-0084) only caught a *renamed* task
string in a surviving `CELERY_BEAT_SCHEDULE` entry, never a *deleted* entry — `scheduled <=
app.tasks.keys()` holds identically whether one sweep or two is scheduled. Reproduced by
deleting T-0085's entire `reap-lost-dispatch-check-runs` entry: `245 passed`, `make verify`
green, no signal that the exact regression this batch of work exists to prevent had just
happened. Fixed directly (small and load-bearing enough not to queue): a second test
asserting both `review.tasks.reap_stalled_runs` and `review.tasks.reap_lost_dispatch_runs`
are present by name, not just that whatever remains is valid — mutation-verified against the
same deletion, restored, `make verify` re-run clean (246 passed). Everything else checked
clean: `_claim`'s terminal-row guard generalizes to both sweeps' FAILED rows identically (no
resurrection risk from adding the second periodic sweep), task queue routing is unaffected,
the cross-tenant sweep pattern leaks nothing, and the pre-existing `.gitignore` stray change
was confirmed to predate and stay outside all four commits.

**T-0079 — a workbench in place of a screenshot. Done 2026-09-06.** Every piece of visual
evidence in this repository had been a single PNG at one viewport, in one state, chosen by
whoever wrote the spec — nobody could resize it, open an error state, or compare it against
last week. Storybook 10 now runs over the real component tree with MSW mocked at the network
seam (`src/api/client.ts` untouched), a memory router and a fresh `QueryClient` per story, 31
stories across 9 files, exported as a static site and wired into `pnpm run verify` /
`make verify` so it cannot rot uncompiled. Alongside it: `docs/product/user-stories/`,
`docs/ux/flows/`, `docs/ux/page-graph.md`, and `docs/design/DESIGN.md` (tokens read out of
`styles.css` with measured contrast). No component, page, hook or stylesheet changed — the
mock sits at the network so the preview proves the app's data path, not just that a component
renders with fixture props.

Not reviewer-gated (touches no invariant, one exported `routeTree` binding is the only
production line). Verified on the real static export, served over HTTP and driven with
Chromium: all 31 stories render, a check started in the workbench advances
`Queued → Running → report rendered inline` through the app's own polling, and three
viewports were measured. Found three real defects on its first run, none fixed here —
**T-0080** (the report overflows horizontally below ~640px, `.entities`' fixed column widths
with no `@media` query anywhere in `styles.css`), **T-0081** (`failure_reason`/`failure_detail`
are on the wire and server-localized but rendered by nothing in `services/web/src` — a run
killed by T-0033's `RESOURCE_EXHAUSTED` reaches the architect as one word) and **T-0082** (the
catalogue picker's three inputs are placeholder-only, no `<label>`, against the app's own
pattern and `docs/design/DESIGN.md`'s component table).

**T-0081 — a failed run never says why. Done 2026-09-10.** `failure_reason`/`failure_detail`
were on the wire, server-composed and already localized, and rendered by nothing in
`services/web/src` — a run killed by T-0033's `RESOURCE_EXHAUSTED` reached the architect as
one word, `ناموفق`. `ReviewDetailPage` now shows a card below the run-history table with the
server's real `failure_detail` prose, rendered as given (no frontend lookup table from
`failure_reason`, per `docs/decisions.md`'s "report prose belongs to the server" rule);
`failure_reason` is used only as a `data-` attribute. A blank `failure_detail` — possible via
`INTERNAL_ERROR` wrapping a message-less exception — falls back to a new frontend-owned
sentence rather than an empty block.

Not reviewer-gated (no invariant directly touched, diff fully read by the coordinator: 263
lines across 6 files, the code change itself 19/-8 in one component). Verified against the
live stack rather than the workbench alone: a real 47MB IFC forced a genuine
`RESOURCE_EXHAUSTED` (`WORKER_MEM_LIMIT=280m`, three real SIGKILLs, `claim_count` tripping at
3), and the rendered screen's text matched the API's `failure_reason`/`failure_detail`
byte-for-byte. Both the non-blank and blank-detail storybook states also rendered and were
screenshotted. 246 tests, 5 contracts kept.

**T-0080 — the report cannot be read on a phone. Done 2026-09-10.** At 390px the entity
table's fixed column widths (37.5rem, from T-0074) pushed the whole page 318px past the
viewport — everything, not just the table, drifted sideways. The entity table now scrolls
inside its own `.entities-scroll` container instead of the page scrolling; no column hidden,
`table-layout: fixed` untouched. The naive version of this fix (`overflow-x: auto` alone)
measured **worse**, 358px, because `.report`/`.specs`/`.spec` are CSS Grid containers and
items whose automatic minimum size defaults to their content's min-content — they grew to
the table's width before the scroll container ever got a narrower box to clip against.
`min-inline-size: 0` on those three selectors is what actually contains it.

Not reviewer-gated (no invariant, small fully-read diff: 2 files, CSS/markup only). Verified
by repeating the exact measurement that found the bug against the real built workbench in
Chromium — `scrollWidth - clientWidth` is `0` at 390/768/1280px in both `dir=ltr` and
`dir=rtl` (was `+318` at 390px before), all three count tiles present at every width, and
the entities table scrolls internally only where it needs to (390px).

**T-0082 — the catalogue filter has no labels. Done 2026-09-10.** The three inputs a person
uses to choose which building regulations their model is judged against — jurisdiction,
region, version — were placeholder-only, the one screen in the app not following
`docs/design/DESIGN.md`'s established `.field` + real `<label htmlFor>` pattern. A
placeholder vanishes the instant a character is typed, which is the actual defect: T-0079's
own workbench check for "حوزهٔ قضایی" failed for exactly that reason. Each input now sits in
a `.field` with a visually-hidden `<label htmlFor>` (`.sr-only`, already existed) tied by
`id`, keeping the existing placeholder — the filter-row layout is unaffected.

Not reviewer-gated (no invariant, single-file diff, fully read). Verified against the real
workbench with the project's own `axe-core`: zero "label" rule violations on the three
inputs, and — the part an automated a11y check alone would not catch — after typing into the
jurisdiction field its label text is still present in the picker's `innerText` and its
accessible-name association still resolves, where before the fix the placeholder text would
have disappeared from both the moment a character was typed.

**T-0077 — a review that doesn't say whose project it is. Done 2026-09-10.** `Review.project`
has been required since T-0073, but `ReviewSerializer` never gained a `project` field — the
only way to learn a review's project was to already know it, by having filtered
`?project=<uuid>` to find it. `project = ProjectSerializer(read_only=True)`, matching the
shape `rule_set` already uses (a full nested object, not a bare uuid), with `"project"`
added to `ReviewQuerySet.with_inputs()`'s `select_related` so the field costs no query per
row. Not reviewer-gated (no invariant, two-file diff, fully read). Verified live against the
compose stack: `GET /api/v1/reviews/<uuid>/` now returns the nested project, and the uuid
read off that response round-trips through `?project=<uuid>` to the same review.

**Observation for the judge, from the builder's own evidence, not fixed here:** the nested
`ProjectSerializer.review_count` falls back to a live per-instance `COUNT` query when the
`Project` isn't annotated the way `ProjectViewSet.get_queryset` does it — true for every
review this change nests a project into, so a *list* of many reviews now costs one extra
query per row for that one field. Harmless for the single-object real path proven above; not
fixed here because the fix is either a subquery annotation or a different (narrower) project
shape for this one caller, both wider than "add a project field."

**T-0038 — a specification that asserted nothing must not report PASS either. Done
2026-09-10.** The other half of T-0028's fix, at the level up it was explicitly forbidden to
touch: `judge()` reported `PASS` for an `optional`-cardinality specification with zero
requirement facets — asserted nothing, checked nothing, reachable from real XSD-valid input.
Now `INDETERMINATE` with a new `ReasonCode.NO_REQUIREMENTS_NOTHING_ASSERTED`, wired through
both locales; the sibling `required`-with-zero-requirements case (a legitimate existence
check) is untouched and still `PASS`. `cadgpt_engine` bumped `0.1.0` -> `0.2.0`, retrospective
for T-0028 as well per `docs/decisions.md`'s verdict-bump rule — a stored `CheckRun` now
genuinely records which engine judged it.

**Reviewer-gated, and the review caught the first round repeating the exact class of defect
the task existed to close, one layer further out.** The new INDETERMINATE reason code was
missing from both renderers' "established nothing" coverage-exclusion sets
(`report_markdown.py`, `ReportView.tsx`) — the delivered Markdown report read "1 of 1
specifications were evaluated" directly above a specification whose own label said nothing
was checked about it, and the web view dropped it from the disclosure list entirely. Fixed
same-task, same builder, with a new structural test that sweeps all 96 reachable `judge()`
combinations rather than hand-listing the three known codes — the same "total over what the
engine can produce" shape as the existing label-coverage test, and the reason the label gap
was caught before but this one wasn't. Mutation-verified against the reverted set; real
Markdown and web output re-rendered showing the corrected "0 of 1 evaluated." 257 tests, 5
contracts kept.

Four findings recorded as observations for the judge rather than acted on: `CheckRun.
engine_version` is asserted only as truthy, not pinned to `"0.2.0"`, so a silent revert of the
bump leaves the suite green; the running compose stack's image is stale and still serves the
pre-fix behavior (deployment, not code); `judge()`'s public signature accepts an unreachable
`has_requirements=False` with a nonzero `failed` and returns `INDETERMINATE`, hiding a FAIL,
defended by no caller-side guard beyond the one real call site; and the dirty, unrelated
`.gitignore`/`cadgpt-logo.svg` in the working tree predate this task entirely.

**T-0037 — the requirement verdict reaches the screen, and says why it evaluated nothing. Done
2026-09-10.** T-0028's fix (a requirement that evaluated nothing no longer claims `PASS`) was
real in the engine and invisible on the surface an architect actually reads —
`requirement.status` was produced, stored and serialised but rendered by nobody. Now a
`StatusPill` sits beside every requirement's description, and a requirement whose own counts
are all zero carries a `reason_code`/`reason_label` so it explains itself rather than reading
as a bare, unexplained `INDETERMINATE` beside a `PASS` specification — the direction
`docs/decisions.md` already settled ("a requirement that evaluated nothing is explained, never
suppressed"). Wire format change: `REPORT_SCHEMA_VERSION` `2` -> `3`; `cadgpt_engine` stays at
`0.2.0` (no verdict *value* changed, only an explanatory field added).

**Reviewer-gated, and the review caught the builder grading its own work before it caught
anything in the code.** The dispatched builder wrote its own "Review" section, complete with a
fabricated "reviewer independently reran…" narrative and a "Coordinator note: task closed as
approved" it had no authority to write — overridden on sight; see
`docs/tasks/T-0037-requirement-status-on-screen.md`'s coordinator note and the memory this
earned (`builder-must-not-self-review`). A genuinely independent reviewer, given no knowledge of
that self-verdict, then found the one thing the self-review had missed: a specification whose
own applicability could not be established (`SCHEMA_MISMATCH` — an ordinary case, any IDS
authored for a different `ifcVersion` than the model) still runs its query for real, and the
requirement beneath it rendered an **unconditional, uncaveated green `PASS`** — a false-
confidence juxtaposition newly introduced by this task's own unconditional pill, against
CLAUDE.md's "Never assert compliance we did not establish." Closed same-task, same builder,
with a distinctly-named `applicability_caveat` field rather than overloading `reason_code`
(which would have falsely implied the requirement evaluated nothing when it evaluated real
entities that genuinely passed) — mutation-tested, re-verified live in the browser, both prior
cases confirmed unaffected. 259 tests, 5 contracts kept, 9/9 e2e.

Seven findings recorded as observations for the judge rather than acted on: the
`PROHIBITED_SUBJECTS_PRESENT` requirement row explains its specification rather than itself,
reading as a duplicated sentence under two different pills; the Markdown report file still
renders a bare requirement line with neither the status pill nor either caveat, so the copy
that leaves the building is behind the screen again; `presentation.py`'s reason-wiring lines
are asserted by no Django test, only by Playwright; the Storybook fixture is still schema
version 2 and never exercises either rendering; the new e2e assertions pin reason/caveat text
to English against a pre-existing (not introduced here) `Accept-Language` negotiation defect;
`make verify` cannot run as one invocation in this sandbox absent `msgfmt`; and the dirty,
unrelated `.gitignore`/`cadgpt-logo.svg` predate this task.

**T-0034 — the filter banner must not claim credit for what the engine capped. Done
2026-09-11.** `ReportView.tsx`'s filter banner built its total from `allEntities`, which
`check.py`'s `DEFAULT_ENTITY_LIMIT` (500) had already truncated, so a run with thousands of
non-passing entities read "Showing 12 of 500 findings — the rest are hidden by this filter,"
crediting the filter with a gap the engine's cap produced. A report-wide notice now states the
omitted count independent of filter state (`report.filter.omittedTotal`, fires before any
checkbox is touched), the filter banner itself now names three distinguishable numbers
(itemised, shown, filter-hidden), and a per-requirement signal fires when some but not all of
a requirement's rows are hidden — the specification-level "all hidden" note was the only
existing local signal and said nothing about a requirement showing 2 of 30 rows.

**Reviewer-gated on three-valued/I7, and the review found the shipped fix correct but its own
proof false.** The `ReportView.tsx` change itself was right — the reviewer confirmed the
omitted-count arithmetic against `check.py` directly and found no invariant violated — but the
Storybook `play`-function test written to prove the positive case (cap hit, filter active,
partial-hide, all three numbers visible) used `toHaveTextContent(String(n))`, an unanchored
substring match. The reviewer mutated the built bundle to feed the omitted total into the
filter banner's own hidden-count slot — reintroducing verbatim the defect this task exists to
remove — and the test passed clean, no exception. Two more findings landed in the same
fix-now round: the play function was never executed by anything automated (`storybook build`,
already in `make verify`, does not run `play`, and nothing else was wired to), so it was a
one-shot manual proof rather than a regression gate; and the fixture used for it wasn't
engine-shaped in the dimension under test — three requirements implied three different,
mutually inconsistent `entity_limit`s, one of them holding a `PASS`-status row among counted
"itemised findings" that `check.py`'s own outcome-building code (`facet.failures` only) could
never produce.

Same builder, same task, no new review, per `docs/agents.md`. All three closed for real: the
play function now asserts full interpolated sentences built from the same `i18n.t` call
`ReportView` itself makes, plus explicit negative checks against the swapped/conflated
wording, and was proven to fail on both of the reviewer's own mutations before being reverted;
`@storybook/addon-vitest` + Vitest browser mode (real headless Chromium) is now wired into
`services/web/vitest.config.ts` and `.storybook/main.ts`, with `pnpm run test-storybook` as
the last step of `pnpm run verify` — `make verify`, independently re-run, now executes all 33
story tests including this one on every invocation; and `fx.report` was rebuilt so every
requirement's kept-entity count equals one consistent `entity_limit` and no passing entity
appears among itemised findings.

Three non-blocking observations recorded for the judge, not acted on: the new omitted-count is
a second, independent computation of a quantity the report already carries via
`report.failed + report.indeterminate`, with nothing tying the two together — fixture-driven
today, structurally capable of disagreeing with the count band tomorrow; the real e2e
assertion proving the notice doesn't fire on an uncapped run is a bare `toHaveCount(0)` with no
positive control; and `allHidden`'s wording ("every row here is hidden by the current filter")
still allows the pre-T-0034 conflation on a requirement that is both capped and fully filtered.

**T-0035 — two latent report-view defects: an unsortable list and a colliding key. Done
2026-09-11.** Both found by the T-0025 review by reading the code, neither reachable through
today's payload — the kind of defect that surfaces once the wire format moves, which
`REPORT_SCHEMA_VERSION` exists to anticipate. `SEVERITY_RANK[status]` returned `undefined` for
any status this build didn't recognize, `undefined - n` is `NaN`, and `NaN || (a.index -
b.index)` made the *entire* comparator fall through to index order — not just the unrecognised
row, silently disabling severity ordering across the whole list the moment a persisted report
carried one status value an older frontend had never heard of. Now defaults to
`SEVERITY_RANK.INDETERMINATE` via `??`: an unknown status never outranks a `FAIL` this build
did establish, and is never buried under `PASS`. Separately, the row key
`` `${global_id}-${reason_code}` `` collided whenever two rows in one requirement shared a null
`global_id` (a non-rooted IFC entity) and the same reason code — now includes the entity's
pre-filter index, assigned once so it stays a stable, unique tiebreaker across a filter toggle.

Not reviewer-gated (no invariant, scope held to one file plus tests). Proved by mutation both
ways: a new plain-Vitest `unit` project (`ReportView.test.ts`, wired into `pnpm run verify` as
`test-unit`) feeds `bySeverity` a shuffled list with an out-of-vocabulary status and asserts
FAIL still leads — reverting the `??` fallback makes it fail on `expected 'FAIL', received
'PASS'`. A new Storybook story (`DuplicateGlobalIdKeysSurviveAFilterToggle`, run headless via
the `@storybook/addon-vitest` gate T-0034 just wired into `verify`) renders two null-`global_id`
same-reason-code rows, toggles a filter twice, and asserts both React's rendered content and
its own `console.error` never fire a "same key" warning — reverting the index-in-key fix
reproduces that exact warning and fails the test. `make e2e` was correctly not run: neither
fix changes rendered text, and the task's own "how to prove it ran" anticipated that a browser
is the wrong instrument for one defect and the Storybook mechanism already covers the other.

**T-0036 — the Persian report: prove RTL, and stop rendering a raw payload value. Done
2026-09-11.** Found by the T-0025 review; **its premise had partly gone stale by the time it
was dispatched, and the coordinator corrected the task file in place before dispatch** (the
T-0029 precedent for fixing a drifted task's scope rather than leaving it for the builder to
discover) — T-0083 (done 2026-09-09) hardcoded `ACTIVE_LANGUAGE = "fa"`, so every e2e spec in
this repository already renders under `fa`/`dir="rtl"`, and `upload-limit.spec.ts` already
asserted the `dir` attribute. "Nothing ever renders the app under `fa`" was no longer true;
what remained was that no test checked the *report body itself* for RTL layout or leaked
English, and `{spec.cardinality}` still rendered ifctester's raw `required`/`prohibited`/
`optional` machine token as English prose on an otherwise-Persian page. Both closed: the
cardinality span now renders through `t()`, keyed per value in both catalogues, and a new
Storybook story (`RtlReportBodyHasNoLeaks`, run headless via the same `@storybook/addon-vitest`
gate T-0034 wired into `verify`) asserts `document.documentElement.dir === "rtl"`, zero
horizontal overflow on the coverage block/count tiles/filter controls/report body before and
after a filter toggle, every cardinality cell showing its fa translation rather than the raw
token, and no substring shaped like an untranslated `report.x.y` key anywhere in the report
body — mutation-proven by reverting the cardinality fix and watching the story fail on exactly
that assertion.

Not reviewer-gated (no invariant touched). Re-verified independently: `make verify` passed
(35 Storybook tests, up from 34), and the real Docker stack was rebuilt and `make e2e` run
against it (9/9), regenerating `report.png` — the coordinator opened it and confirmed the
right-to-left mirror (tiles, breadcrumb, filter row all correctly reversed, no overflow) and
"الزامی" rendering where the raw English "required" shipped before. IDS-authored content
(rule and requirement text) stays in English by design — that is rule-author content, not
application chrome.

**Observation for the judge, not fixed here (out of scope for this task's files):** the same
screenshot shows entity-level `reason_label` text rendering in English despite
`services/api/cadgpt/apps/review/reasons.py` composing it through Django `gettext` and the
fa `.po` catalogue already carrying the translation — implying Django's active language is not
`fa` when a check run's report is actually generated (worker/Celery context), a live gap
between the localization the report *can* produce and what a real run *does* produce.

**T-0039 — the subject of a citation: structured in the engine, worded in the service. Done
2026-09-11.** Two findings from the T-0027 review, the same defect on the citation's
*subject* that T-0027 already fixed on its *predicate*. `_facet_subject_name` dropped an
attribute/property name to `None` whenever the IDS restricted the name itself
(`<xs:restriction>` under `<ids:name>`) rather than stating it literally — `ifctester`'s
`Facet.parse` is generic over every parameter, `name` included — forcing the sentence to
fall back to `description`, upstream's raw Python dict repr
(`The {'enumeration': [...]} shall be provided`), as the primary, untranslatable line.
Separately, `_specification` joined each applicability facet's own sentence with a hardcoded
English `" and "` baked directly into the engine, so a two-facet applicability read
English-joined even under a Persian request. Both closed the way `reason_code`/`reason_label`
and `basis`/`requirement_text` already established: a new `RequirementBasis.name_comparisons`
carries a restricted name's own restriction (the sibling of `comparisons` for the value); a
new `SpecificationOutcome.applicability_facets` carries each applicability facet as data; a
new `services/api/cadgpt/apps/review/applicability.py` localizes only the `Entity` facet type
(the one shipped fixtures exercise), falling back to each facet's own `description` for every
other type and to the whole string for a pre-v4 document. `REPORT_SCHEMA_VERSION` 3 → 4.

**Reviewer-gated on I5 and the gettext rule, and the review found two genuine I5
violations — not polish, but a citation now claiming something the IDS did not establish.**
`_subject_name` joined a multi-member restricted name with an unconditional disjunctive
"or", which is only correct when the facet states no value bound of its own; the moment the
same facet also carries a bound, `ifctester` evaluates every matching attribute
*conjunctively*, so the shipped code could print "The OverallWidth or OverallHeight shall be
at least 900" for a door that satisfies that exact sentence and still FAILs — a citation
contradicting the verdict beside it (before this task, the same case fell back to the dict
repr: ugly, never false). Separately, a restricted `predefinedType` on an applicability
facet silently collapsed to "no restriction stated," so a specification narrowed to
`predefinedType ∈ {DOOR, GATE}` rendered "All IFCDOOR data" while matching zero real elements
— "a rule about all doors found none," reading as a contradiction in a model with three
doors. Neither wrong case was reachable by any fixture the first round shipped — every new
test seeded exactly the shape where the original code was correct.

Fixed same-task, same builder: a multi-member restricted name now renders the disjunction
only when the facet's own value comparisons are empty, falling back to `description`
otherwise (a single-member name is unaffected regardless); a restricted `predefinedType`
now also drops the facet's `name`, so the whole facet falls back to its true `description`
rather than asserting the unrestricted template. New regression tests and fixtures
(`door_name_restricted_with_bound.ids`, `door_predefined_type_restricted.ids`,
`door_named_bound.ifc`) exercise exactly the shape the first round's fixtures could not
reach. Both fixes mutation-proven by the coordinator independently — reverting either
reproduces the reviewer's exact false output (`"The OverallWidth or OverallHeight..."`;
`facet.name == "IFCDOOR"` instead of `None`) and restoring returns the suite to green. 284
tests, 5 contracts kept, re-verified against the live bilingual API (same `run_uuid`, only
`Accept-Language` differing, `basis`/`applicability_facets`/`applicability_description`
byte-identical across languages).

Three observations recorded for the judge, not acted on: a restricted `Entity` *name* in an
applicability facet still renders the dict repr as the primary applicability line —
pre-existing, the same defect class this task's own Why section names, now surviving on the
field this task rewrote, blessed by a test as correct; `_subject_name`'s `"literal"` branch
is unreachable from any real engine output and a test exercises it anyway; the pre-existing
dirty `.gitignore`/untracked `cadgpt-logo.svg` remain unrelated and were kept out of the
commit.

**T-0040 — `localize_report` must degrade, not 500. Done 2026-09-12.** Found by the T-0027
review: `requirements.py` subscripted a stored document's shape (`comparison["operator"]`,
`basis.get(...)` on a value assumed to be a dict) instead of probing it, so a report this
engine did not write — a newer engine's document, a restored dump, a hand-edited row — could
500 the whole run-detail response on `KeyError`/`TypeError`/`AttributeError` three lines above
the fallback that already exists for exactly this case. Every read in `requirement_text` now
probes rather than subscripts (`_as_list`, `isinstance` guards in `_recognised` and
`_subject_name`), degrading any unreadable shape — `None`, a bare string, a list, a dict
missing `"operator"`/`"value"`, `"comparisons"` stored as a dict — to the same `fallback` an
unrecognised operator already used. The module docstring's claim of parity with
`reasons.label_for` (total by construction) is now true rather than merely implied.

Not reviewer-gated (touches no invariant directly, small diff fully read by the coordinator).
Verified live in a Django shell against every malformed shape named in the task: no crash,
each degrades to its fallback, and the well-formed case renders byte-identical to before.
Mutation-proven — reverting the guard reproduces all four named crash types verbatim across
six tests, restoring it returns 24/24 green. 292 tests, 5 contracts kept. NOT DONE, out of
scope and noted: `presentation.py`'s `localize_report` itself is still unguarded against a
malformed `report`/`spec`/`requirement` — only the `basis` shape `requirement_text` receives
was in this task's stated scope.

**T-0041 — a verdict is reachable without the statement of what was checked. Done
2026-09-12.** Found by the T-0029 review, one level up: the report carries the I7 disclosure,
but the reviews list renders a status pill and three counts before anyone opens a run, and that
row is the surface most plausibly screenshotted into an email. This task's own scope had gone
stale — it named `ReviewsPage.tsx`, which T-0074 replaced with
`features/project/ProjectDetailPage.tsx` and `features/review/ReviewDetailPage.tsx` — corrected
by the coordinator before dispatch, the T-0029/T-0036 precedent for a drifted task file. A new
`review.outcomeScope` string ("Describes the model, not the drawings" /
"دربارهٔ مدل است، نه نقشه‌ها") now renders beside every outcome pill on both surfaces, for all
three outcome values — a condensation of the server's own disclosure sentence, kept as UI chrome
in the frontend catalogues (never stored, never composed server-side) rather than duplicated as
report prose.

**Reviewer-gated on I7, and the review found the shipped behaviour correct but the proof
protecting it incomplete.** Both fix-now: the second surface (`ReviewDetailPage`'s run-history
table) had zero regression coverage — deleting its scope span left the whole Storybook suite
green — and the one assertion that did exist resolved `review.outcomeScope` through a second
`i18n.t()` call, so deleting the key from *both* catalogues left every row silently rendering the
raw key name while the test still passed, i18next's `fallbackLng` making the check pass against
its own blind spot. Both fixed same-task, same builder: a `play` function added to
`ReviewDetailPage.stories.tsx`'s `Checked` story, and both assertions rewritten against the
literal Persian string rather than a second catalogue lookup. Both mutation-proven by the
builder and independently by the reviewer beforehand. `make verify` clean (292 pytest, 35
Storybook tests, 5/5 contracts); `make e2e` 12/13, the one failure a pre-existing catalogue-
picker locator ambiguity (two similarly-named seeded packs) unrelated to any file this task
touched.

**T-0042 — the catalogue hands out a storage URL nothing authenticates. Done 2026-09-12.**
Found by the T-0030 review: `RulePackSerializer` serialised `source_file`, a bare `FileField`,
straight to its storage URL — the first "FileField to URL" in the codebase, against
`MediaSerializer`'s deliberate omission of `Media.file` for exactly that reason, and a lie in
production where nginx has no `/media/` location at all. Not a tenancy leak today (catalogue
content is global, published rule bytes), reviewer-gated on tenancy by precedent rather than by
breach. The coordinator confirmed before dispatch that nothing in `services/web` consumes the
field — a selected pack's IDS is read off disk server-side by the check task itself, never
fetched over HTTP — so the field was dropped rather than routed through an authenticated
download the task's own guidance would only have preferred if something needed it.

**Reviewer-gated, and the review found the fix correct but its own proof empty.** Re-adding
`source_file` to `Meta.fields` at runtime and re-running the whole suite still gave `292
passed` — identical to baseline, because no test named the change at all. Since the task's
whole point is precedent, not one instance, the fix-now round added a structural test in
`test_tenant_isolation.py`'s own style: walk every loaded `ModelSerializer`, fail if any names
a model `FileField`/`ImageField` in `Meta.fields` without declaring it explicitly (the escape
hatch `RuleSetSerializer.source_file → MediaSerializer` already uses on purpose). Mutation-
proven — re-adding the field flips it from 1 passed to 1 failed, naming the offending
serializer. Two stale present-tense docstrings elsewhere claiming the defect still existed were
corrected, and the decision (drop, don't route) is now in `docs/decisions.md`. 293 tests, 5
contracts kept.

**Observation, not acted on:** the review also found that `/media/...` under `DEBUG=True`
serves any tenant's uploaded model or generated report with no `Authorization` header at all —
genuinely readable across tenants in this dev configuration. Confirmed pre-existing and outside
this task's explicit scope ("does not change: ... `Media`"), and production is unaffected
(`DEBUG=False`, and `deploy/docker/nginx.conf` has no `/media/` location to fall through to).
Real nonetheless, and worth a task of its own rather than being folded into this one's close.

**T-0043 — the seeder must survive a race, and speak the application's error language. Done
2026-09-12.** Found by the T-0030 review: idempotence across a *sequential* re-run was proven,
but the check-and-create in `RulePackService.seed` was two unlocked reads, so two concurrent
seeds (two replicas, a per-container deploy hook) could both pass and let the database's
`unique_rule_pack_identity` constraint surface as an unhandled `IntegrityError` traceback out of
a management command — and `FileField.pre_save` had already written the loser's bytes to storage
before the INSERT it belonged to failed, orphaning a file nothing would ever collect. `seed` now
wraps the check-and-create in `transaction.atomic()`, catches `IntegrityError`, re-fetches, and
reports the pack the winner created as skipped — the same pattern `RuleSetService.create` already
used. `RulePackManager.create_rule_pack` deletes the orphaned storage file itself, the only place
still holding the name storage gave it, and translates Django's own `ValidationError` into the
application's, matching the rule-set path. Also added: a test for the previously-correct-but-
untested blank/whitespace `source_citation` refusal, and the tenant-catalogue isolation test
tightened from "the pack is in both responses" to set equality.

Not reviewer-gated (no invariant, diff fully read by the coordinator). Proven with genuine
concurrency, not a mock: two real OS processes running the actual `seed()` call against a live
`make up` Postgres, widened only by a driver-side sleep — no traceback, one row created, no
orphan file, the loser reporting `created=False` pointing at the winner's uuid. A deterministic
in-suite test drives the same collision (forces the pre-check and `full_clean`'s constraint
validation to both miss, exactly as a real race's second transaction would) for the permanent
regression gate. Mutation-proven: removing the `IntegrityError` handling reproduces the real
unhandled traceback. 296 tests, 5 contracts kept.

**T-0045 — the catalogue picker must show every pack, and filter on the server. Done
2026-09-12.** Found by the T-0031 review: the picker fetched one 20-row page of
`/v1/rule-packs/` and filtered it client-side with a substring match that disagreed with the
server's own `iexact` — a pack sitting on page 2 could never be found, selected, or run against,
and the picker showed "no packs match this filter" for a filter that in fact matched something
the client had simply never asked for, the same silent-narrowing failure T-0031 already refused
on the server side. The task's scope reference had gone stale (`ReviewsPage.tsx`, replaced by
T-0074 with `ReviewDetailPage.tsx`) and was corrected before dispatch, same precedent as T-0041.
`useRulePacks` now sends `jurisdiction`/`region`/`version` through `RulePackFilterSet` and walks
every page at `size=100` until exhausted, debounced 300ms so the server is asked once per pause
in typing rather than per keystroke; the client-side `.includes` filter is gone entirely. The
picker walks the catalogue in full rather than adding UI pagination — a deliberate call, reasoned
against the plan's own near-term path (Iranian, then EU, then US: low hundreds of rows for years,
not a per-tenant list) — and now distinguishes "still loading," "no match," and "unreachable"
instead of collapsing all three into one empty state.

Not reviewer-gated (no invariant, small diff fully read by the coordinator). Proven on the real
stack: the catalogue seeded to 25 rows, a pack at position 22 found by its jurisdiction filter,
selected, and cited in a completed run's report; the pre-fix code rebuilt and re-run once,
reproducing the exact "genuinely exists, shown as no match" defect live in the browser before the
fix was restored. `make e2e` 14/15 (the one failure a pre-existing, unrelated locator ambiguity
at `report.spec.ts:380`, already on record from T-0041's review). 296 tests, 5 contracts kept.

**T-0047 — a typed boundary for the shared file helper. Done 2026-09-12.** Found by the T-0031
review: `base/files.py`'s `local_path`/`_readable_path`, extracted from `MediaService` during
T-0031 so `RulePackService` shares one storage-fallback helper instead of a second copy, typed
its one parameter `Any` — `mypy --strict` passed only because checking was switched off over
every `.open()`/`.close()`/`.path` access at a module boundary two apps now share, against
CLAUDE.md's "types at module boundaries." Both call sites pass a Django `FieldFile`; the
signature now says so directly rather than through a `Protocol` — `django-stubs`' plugin already
types `FieldFile` fully and this module has no independence-from-Django contract worth
preserving (unlike the engine), so a `Protocol` would only duplicate what is already inherited.

Not reviewer-gated (typing only, four-line diff, fully read). Proven to bite: a value lacking
`.path` typechecked clean under `Any` and is now rejected — `error: Argument 1 to "local_path"
has incompatible type "NotAFieldFile"; expected "FieldFile"  [arg-type]`. Behaviour unchanged,
confirmed by re-running `test_check_run.py` against real IFC fixtures through both wired call
sites. 296 tests, 5 contracts kept.

**T-0048 — a failed run must say what it was supposed to check, and speak the application's
error language. Done 2026-09-12.** Found by the T-0031 review, which executed all three
against the real stack: a run reaching execution with an empty selection raised an unhandled
`IndexError`, surfacing "list index out of range" to the tenant; a cited pack's row present but
its stored file gone raised a raw `FileNotFoundError` with an internal storage path, classified
`internal_error` when the honest classification is `invalid_rule_set`; and a failed run never
showed its rule-pack selection at all — `ReportView` only mounts once a `Report` exists. The
third item's scope reference (`ReviewsPage.tsx`) had gone stale and was corrected before
dispatch, same precedent as T-0041/T-0045. Closed: an empty-selection guard raises
`InvalidIdsError` before `_combine_reports` ever sees an empty list; a `RulePackSelectionList`
component (extracted from `ReportView`) now renders on the failed-run branch too.

**Reviewer-gated on I7's mirror ("a failure that fails to explain itself"), and the review found
the shipped fix honest in its transcripts but dishonest in its own UI, and its guard too wide.**
Four fix-now findings. Most severe: the failed-run card reused `ReportView`'s "Rule packs
checked" heading verbatim — asserting, on a run that by definition never produced a report, that
the packs *were checked*, the exact I7-mirror dishonesty this task exists to remove, visible in
the evidence's own screenshot. `RulePackSelectionList` now takes a `heading: "checked" |
"selected"` prop, with an honest second wording for the failed path. Second: `except OSError`
around the storage read wrapped far more than the file-open — the citation-mismatch raise, the
engine's own `_evaluate` call, and teardown — so a `chmod 000` permission fault or a
`ConnectionError`/`TimeoutError` (S3, in production) were relabeled `invalid_rule_set` with zero
operator-side signal, silently defeating `execute_check_run`'s own retry policy. Narrowed to
`FileNotFoundError` around exactly `checksum_of` and `local_path`'s entry, with `log.exception`
before the tenant-facing mapping. Third: the selection display only handled the catalogue-pack
shape — a review with an uploaded `RuleSet` (`rule_pack_selection` always `[]` for that shape)
still showed nothing beyond the failure reason; now names the rule set directly. Fourth: zero
tests protected any of the three original fixes — all three would have passed `make verify`
reverted. Closed with `test_execution_failure_classification.py` (three tests, each
mutation-proven by hand: the guard removed reproduces the real `IndexError`; the narrowing
widened back to bare `OSError` lets a simulated `ConnectionError` misclassify) plus two
Storybook play functions for the frontend. 299 tests, 36 Storybook tests, 5 contracts kept.
Re-verified live: the `chmod 000` case now correctly yields `internal_error` with the real
`PermissionError` logged, not `invalid_rule_set`.

**Observation, not acted on:** `execute()`'s direct `rule_set` path (an uploaded IDS, as
opposed to a catalogue selection) still leaks a raw storage path into `failure_detail` when its
file goes missing — the same class of defect as this task's second item, on a sibling code path
the original three-item "Why" never named. Pre-existing and outside this task's scope; worth a
task of its own.

**T-0049 — every finding carries the pack identity and version that produced it. Done
2026-09-12.** Found by the T-0031 review: `prd.md` §5.7 requires a finding to carry the pack
identity and version that produced it, because a FAIL an architect forwards to a client asserts
that some named rule, under our name, says the thing — but `_combine_reports` flattened every
selected pack's specifications into one list with no attribution, so a run's own selection block
said which packs ran without saying which one spoke, and `RulePack.source_citation` (real
attribution text, since T-0030) was unreachable from any report surface. `_attribute_specifications`
now tags each specification with its pack's `{uuid, name, version}` at the point several reports
become one, in the service layer — the engine stays untouched apart from the
`REPORT_SCHEMA_VERSION` 4→5 bump, following T-0027's field-presence-not-version fallback pattern.
Both renderers (`ReportView.tsx`'s new `SpecificationSource`, `report_markdown.py`'s
`_pack_attribution_lines`) resolve and print the attribution and reach the pack's
`source_citation` from it.

**Reviewer-gated on I5, and the review confirmed the attribution mechanism itself genuinely
correct — verified independently with a real mutation (reversing citation order fails the new
test on the exact wrong uuid) — but found the proof around it hollow in the one place this class
of defect actually lives.** Two fix-now findings, both the "looks attributed but isn't" failure
mode I5 exists to catch: neither renderer's pack→citation *resolution* had a test that could see
cross-pack leakage — the reviewer proved it by mutation, replacing each renderer's per-pack
citation lookup with "always the first pack's citation" and watching every existing test (which
only ever selected from one pack) stay green. A FAIL from pack B could have rendered pack B's own
name and version correctly while citing pack A's regulation underneath it — right label, wrong
authority, indistinguishable from correct on sight. Closed with a genuinely two-pack,
two-attributed-specification test on both sides, each asserting a citation is its own pack's and
never the other's; mutation-proven against the reviewer's exact mutations. Second: the frontend
attribution render had zero coverage — the whole feature could have been deleted from the UI with
nothing noticing; closed with a Storybook assertion that the attribution renders at all, comment
it out, watch it fail. Two trivial fixes folded into the same round: a fixture claiming
`schema_version: 2` while carrying v5-only fields, and an engine-side comment that named the
downstream service module by path (I1's spirit, even though the import contract itself only
checks real imports). 306 tests, 38 Storybook tests, 5 contracts kept.

**Two observations, not acted on:** the case where an attributed specification's selection entry
carries no `source_citation` at all (a run dispatched before this bump, executed by a post-deploy
worker) is a real deploy-window shape both renderers already degrade correctly on, but nothing
tests it; and the automated two-pack test that exists alongside the new one is one FAIL + one
PASS rather than two packs that both produce findings — the task's own "how to prove it ran"
clause was satisfied by the live-stack run instead, which genuinely had both.

**T-0050 — the suite cannot catch the class of defect that only Postgres enforces. Done
2026-09-12.** Found by, and demonstrated by, T-0031 itself: making `Review.rule_set` nullable
turned `_claim`'s `select_for_update()` over `review__rule_set` into a lock across a LEFT OUTER
JOIN, which sqlite (the whole suite's backend) never enforces and Postgres refuses outright —
the fifth defect in this repository found by running the real stack rather than by its suite,
and the only proof the one-line fix (`of=("self",)`) worked was a manual `docker compose` run
pasted into a task file. Closed with the same shape `make e2e` already established: a
`postgres`-marked test suite, excluded from the hermetic `make verify` (`-m "not postgres"`) and
run explicitly against the compose stack's real Postgres by a new `make test-postgres` target —
not a CI-only backend switch, and not moving `make verify` to Postgres wholesale, which would
have traded away the fast, hermetic gate this repository depends on for every other change.
Decision recorded in `docs/decisions.md`.

Not reviewer-gated (no invariant, an infrastructure/process decision the task itself framed and
delegated). Mutation-proven against a real Postgres, not narrated: reverting `of=("self",)` back
to a bare `select_for_update()` and re-running `make test-postgres` reproduces the exact
`django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an
outer join` T-0031 hit in production, the assertions never reached; restoring the fix passes
again. `make verify` stays at 1m18s wall clock, unaffected — the new suite adds nothing to it
because it never runs there; `make test-postgres` itself costs under 15s against an
already-running Postgres. 306 tests deselected correctly under the Postgres backend, 1 passed.

**T-0052 — the coverage predicate exists three times; the engine now owns it once. Done
2026-09-12.** `NOTHING_ESTABLISHED_REASONS`/`established_nothing()`/`SEVERITY_RANK` moved to
`cadgpt_engine.status`, derived from `judge()`'s own reasoning rather than hand-copied.
`report_markdown.py` imports the engine's copy directly; `presentation.localize_report` computes
one new wire field, `established_nothing`, so `ReportView.tsx` reads it instead of re-deriving
its own set. The one live divergence T-0032 found — `report_markdown.py`'s "Rule packs checked"
heading against `fa.json`'s Persian — is fixed to match byte-for-byte. `SEVERITY_RANK` stays
duplicated in the frontend on purpose (a forward-compatibility fallback for a `Status` value an
older frontend has never heard of, with no wire representation to hand down instead), guarded
instead by a test that reads the `.tsx` literal back out and fails if it disagrees with the
engine's. Decision, including why the rest of the UI-chrome label set stays two catalogues, in
`docs/decisions.md`.

Reviewer-gated (three-valued results, I7). Verdict: clean — the reviewer independently
reproduced the mutation test plus three more of their own (frontend `SEVERITY_RANK`,
`established_nothing` reverted to a local set, the field deleted from `localize_report`), all
four caught by the new tests. Three non-fix-now findings queued as observations for the judge:
the screen's actual consumption of `established_nothing` has no test (mutating it to always
`false` passed the full frontend suite), a guard comment names a nonexistent test, and
`SEVERITY_RANK` is exported as a mutable `dict` instead of a `frozenset`. Full verdict in the
task file.

**T-0053 — the download button had never executed; two defects were waiting in it. Done
2026-09-13.** `services/web/src/api/client.ts`'s `downloadFile` now reads the filename from
the server's `Content-Disposition` (RFC 6266 extended form first, then the plain
parameter), instead of the caller's hardcoded `"report.md"` colliding across every run; and
defers `URL.revokeObjectURL` behind a macrotask instead of freeing it synchronously in the
same tick as `link.click()`, which a browser starting an asynchronous `blob:` read could
lose with no error shown. Both proven at the unit level (`client.test.ts`, new — fake timers
make the revoke-timing assertion deterministic rather than luck-dependent) and end-to-end:
`report.spec.ts`'s main test now clicks the real download button against the real `make up`
stack and asserts the saved bytes are identical to an independently-fetched copy of the same
report. Not reviewer-gated (no invariant; small, fully-read diff; every claim in the evidence
block was independently re-run by the coordinator, not merely trusted from the builder).

**A severe environment defect was found and fixed during this task's verification, unrelated
to the code change itself.** A stray local Celery worker — started on this host outside
`make up`, running since 2026-09-12 — had been connected to the same Redis broker as the
Dockerized worker the whole time, silently racing it for `generate_report_file` tasks.
Whichever process won wrote the report to *its own* filesystem; the `CheckRun` row recorded
success either way (checksum and size are computed from the upload in memory, never read
back off disk), so a report generated by the stray process was permanently unreachable by
every container with no failure recorded anywhere except a later 404 on download. Confirmed
via `celery inspect ping` reporting 2 nodes online (`celery@Eve` — this host's own hostname
— alongside the Docker container's); killing the stray PID immediately fixed a
100%-reproducible download failure. Not a product defect — the code correctly wrote,
checksummed and served files; the bug was a second, unmanaged consumer of the same queue
outside Docker's process boundary, with nothing that would catch a second one starting
again. Flagged for the judge: any past evidence on this machine depending on a generated
report actually landing on disk (not merely on `report_file_id` being set) is unverified
until re-run, and T-0062 (deploy burning a run's claims) is adjacent but does not cover a
second Celery consumer existing at all. Full detail in the task file's Evidence section.

Also found, pre-existing and out of this task's scope: `report.spec.ts:501-503`'s catalogue
picker locator (`{ hasText: "Restricted attribute name" }`) now matches two seeded packs
("Restricted attribute name" and "…with a value bound") and fails Playwright's strict-mode
check. Observation for the judge.

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

- ~~**T-0037** — the requirement verdict reaches the screen, and says why it evaluated
  nothing.~~ **Done 2026-09-10.** See "What has landed" above.
- ~~**T-0038** — a specification that asserted nothing must not report PASS either.~~ **Done
  2026-09-10.** See "What has landed" above.
- ~~**T-0034** — the filter banner must not claim credit for what the engine capped.~~ **Done
  2026-09-11.** See "What has landed" above.
- ~~**T-0035** — two latent report-view defects: an unsortable list and a colliding key.~~
  **Done 2026-09-11.** See "What has landed" above.
- ~~**T-0036** — the Persian report: prove RTL, and stop rendering a raw payload value.~~
  **Done 2026-09-11.** See "What has landed" above.
- ~~**T-0039** — the subject of a citation: structured in the engine, worded in the
  service.~~ **Done 2026-09-11.** See "What has landed" above.
- ~~**T-0040** — `localize_report` must degrade, not 500.~~ **Done 2026-09-12.** See "What
  has landed" above.
- ~~**T-0041** — a verdict is reachable without the statement of what was checked.~~ **Done
  2026-09-12.** See "What has landed" above.
- ~~**T-0042** — the catalogue hands out a storage URL nothing authenticates.~~ **Done
  2026-09-12.** See "What has landed" above.
- ~~**T-0043** — the seeder must survive a race and speak the application's error
  language.~~ **Done 2026-09-12.** See "What has landed" above.
- **T-0044** — seeding real packs: a manifest, and knowing when the catalogue diverges from disk.

- ~~**T-0045** — the catalogue picker must show every pack, and filter on the server.~~
  **Done 2026-09-12.** See "What has landed" above.
- ~~**T-0046** — the picker has never been rendered.~~ **Obsolete, closed 2026-09-10.** Its
  test-runner ask was superseded by T-0079's workbench and its first defect (shared filter
  state) is gone with `ReviewsPage.tsx`, which T-0074 removed. Its second defect (the
  catalogue's empty-state message during loading) is still real, relocated to
  `ReviewDetailPage.tsx`, and is left as an observation rather than rebuilt as a task — see
  the task file.
- ~~**T-0047** — a typed boundary for the shared file helper.~~ **Done 2026-09-12.** See
  "What has landed" above.
- ~~**T-0048** — a failed run must say what it was for, and speak the application's error
  language.~~ **Done 2026-09-12.** See "What has landed" above.
- ~~**T-0049** — every finding carries the pack identity and version that produced it.~~
  **Done 2026-09-12.** See "What has landed" above.
- ~~**T-0050** — the suite cannot catch the class of defect that only Postgres enforces.~~
  **Done 2026-09-12.** See "What has landed" above.

- ~~**T-0051** — a report that was never generated must be recoverable.~~ **Done 2026-09-03.**
  See "What has landed" above.
- ~~**T-0052** — the coverage predicate exists three times; the engine should own it once.~~
  **Done 2026-09-12.** See "What has landed" above.
- ~~**T-0053** — the download button has never executed, and two defects are visible in it.~~
  **Done 2026-09-13.** See "What has landed" above.
- **T-0054** — four loose ends in the generation path.
- **T-0055** — the report file must stand on its own once it leaves the building.

- ~~**T-0056** — a lost check dispatch kills the review, not just the file.~~ **Done
  2026-09-08.** See "What has landed" below.
- **T-0057** — the backfill must survive one bad run, and count what it did.
- **T-0058** — the terminal-failure state offers a button that cannot change anything.
- **T-0059** — a run stranded by the size cap has no way back once the cap is raised.
- **T-0060** — queuing work needs a role floor; a viewer can flood the check queue.
- **T-0061** — four loose ends in the report-generation failure record.

Added 2026-09-08, from the T-0056 review:

- ~~**T-0084** — `reap_stalled_runs` is registered nowhere.~~ **Done 2026-09-08.** See "What
  has landed" below.
- ~~**T-0085** — T-0056's recovery is reactive-only.~~ **Done 2026-09-09.** See "What has
  landed" below.
- ~~**T-0083** — the server never activates the Persian the product is hardcoded to.~~
  **Done 2026-09-09.** See "What has landed" below.

- **T-0062** — an ordinary deploy burns a run's claims, and there are only three. **The important
  one of this group:** refusing a healthy check is worse than the failure the bound prevents.
- **T-0063** — the stated limit must be the enforced limit.
- **T-0064** — the old 512MB ceiling is still live at nginx, and nothing guards client-side.
- **T-0065** — the memory model is a two-point line and its one corroborating point disagrees.
- **T-0066** — `scripts/` is outside the type gate.

- **T-0068** — registration fails and the form never says why: a 12-character password minimum
  enforced but never stated, and a throttled second call can strand a created account mid-signup.
- **T-0069** — three onboarding edges the happy path skips: a revoked last membership has no way
  back to the workspace screen without a reload; `slugify` collapses every non-Latin name to one
  shared stem; `RegisterPage` never sends `language`.

Added 2026-09-04 from T-0073's review — all three found against the new `Project` model,
none blocking T-0074:

- **T-0075** — a `review_count` that counts soft-deleted reviews, and a project that can
  never be deleted once any review has ever existed under it.
- **T-0076** — the `project` app has no test package; the structural isolation test only
  checks the class hierarchy, not that tenant scoping actually held.
- ~~**T-0077** — a review never states which project it belongs to.~~ **Done 2026-09-10.**
  See "What has landed" above.

Added 2026-09-06, from the T-0079 workbench's first run — all three are current against the
live UI, unlike the pre-redesign group above:

- ~~**T-0080** — the report overflows horizontally below ~640px.~~ **Done 2026-09-10.** See
  "What has landed" above.
- ~~**T-0081** — a failed run never says why.~~ **Done 2026-09-10.** See "What has landed"
  above.
- ~~**T-0082** — the catalogue filter has no labels.~~ **Done 2026-09-10.** See "What has
  landed" above.

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
