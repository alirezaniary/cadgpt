# T-0031 — Choosing which rules to run, recorded so the run stays reproducible

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** tenancy. **Reviewer-gated.**

## Why

The MVP is one sentence: *the user uploads a model, **picks which rules to run it against**, and
gets back a report file.* T-0030 builds the catalogue. This is the middle clause, and without it
the catalogue is a table nobody can reach.

The requirement that shapes this task is not the picking — it is the **recording**. `RuleSet`'s
own module docstring already states the principle for uploaded rules: *a stored rule set is what
makes a run reproducible from its inputs.* `prd.md` §5.7 extends it — every finding carries the
pack identity and version, because a finding asserts that a rule says something, under our name.
A run that records "checked against the catalogue" and not *which packs at which versions* is a
run nobody can re-derive, defend, or compare against a later one. The catalogue will change; the
record of what a given run actually checked must not.

## Scope

**Changes**

- The check-run record gains the selection: which packs, at which versions, were run. Store what
  is needed to reconstruct the run, not a foreign key that a later catalogue edit can silently
  redefine underneath it — a version string or a content hash captured **at dispatch time**.
  Follow how the existing run already records its inputs rather than inventing a second idiom.
- A migration.
- The API accepting a selection when a check is requested, validating it against the catalogue,
  and refusing an unknown or ambiguous pack rather than quietly running a subset. **Silently
  running fewer rules than asked for is the coverage failure this product exists to refuse.**
- The existing single-`RuleSet` path keeps working unchanged. A run cites either an uploaded
  rule set or a catalogue selection; both are legitimate.
- `services/web` — the selection surface, filterable by jurisdiction, region and version, and
  the run's recorded selection shown on the report.
- Both i18n catalogues.

**What explicitly does not change**

- The engine. It already takes IDS files; how they were chosen is not its concern, and
  `packages/engine` must not learn what a `RulePack` is. The import contracts will catch this.
- The catalogue model itself (T-0030) and the Markdown report (T-0032).
- Coverage, the counts, the three-valued discipline.

**One thing to get right.** A selection of several packs means several IDS files against one
model. Decide deliberately whether that is one run with several rule sources or several runs,
say which in the evidence, and make the report's coverage sentence still true under it —
"N of M specifications evaluated" must count across the whole selection, not per pack, or it
resumes claiming full coverage of whichever pack happened to be last.

## How to prove it ran

`make verify` with the 5 import contracts kept, then the real path against the running stack:

```sh
make up
# a real check, selecting from the catalogue, over HTTP
```

Evidence must show:

1. A real HTTP request creating a run with a catalogue selection, and the run record afterwards
   showing exactly which packs and versions it cites — pasted from the API response.
2. The check actually executing against those rules — the worker log line and the resulting
   counts, not just a 202.
3. **A refused selection**: an unknown or ambiguous pack rejected with a named reason, not
   silently dropped. Paste the response.
4. **Reproducibility**: change the catalogue after a run (bump a pack's version, or add one) and
   show the completed run still reports what it originally checked.
5. Tenancy: a run's selection is visible to its own tenant and not to another.
6. **Wiring**: the migration at head, the route quoted from the router, and the serializer field
   that carries the selection.

## Evidence

### The deliberate decision: one run, several rule sources

**One `CheckRun`, several rule sources.** `CheckRunExecutor._evaluate_selection` (`services/api/
cadgpt/apps/review/services/execution.py`) calls `cadgpt_engine.run_check` once per selected
pack — the engine's signature is untouched, one IDS path per call, exactly as it already was —
and a new `_combine_reports` concatenates every pack's `Report.specifications` into one tuple
and sums the six counts before the result is stored on a single `CheckRun.report`. The
alternative (several runs, one per pack) was rejected because it makes "N of M specifications
evaluated" a per-pack sentence again — full coverage of whichever pack renders last, the others
a click away. `services/web/src/components/ReportView.tsx`'s `evaluated` computation
(`report.specifications.length - nothingEstablished.length`) needed **no change at all** for
this to hold: it already sums over whatever `report.specifications` contains, and a combined
report simply hands it more of them. Proven below (item 2): a 2-pack selection produces one
`CheckRun` whose `report.specifications` has 2 entries, one per pack, and the coverage math is
exact. Full reasoning in `docs/decisions.md`, "A selection of several packs is one run with
several rule sources".

The selection itself is stored as data, never a foreign key: `CheckRun.rule_pack_selection`
(`JSONField`) holds, per pack, uuid/name/jurisdiction/region/version and a SHA-256 of the IDS
file's bytes, computed by `RulePackService.snapshot` at dispatch time inside `ReviewService.
request_check` — before the `CheckRun` row exists.

**A real defect the real path found, not the test suite**: with `Review.rule_set` now nullable,
`CheckRunExecutor._claim`'s `select_for_update()` over `select_related("review__rule_set")`
became a lock across a LEFT OUTER JOIN. `make verify` (sqlite) was green throughout; the first
real check against the compose stack's real Postgres failed with `NotSupportedError: FOR UPDATE
cannot be applied to the nullable side of an outer join` — sqlite never enforces that
restriction. Fixed with `select_for_update(of=("self",))`, restricting the lock to `check_run`
itself; full traceback and fix are in `docs/decisions.md`. `make verify` and the HTTP evidence
below are both from *after* this fix.

### `make verify` — green, all 5 import contracts kept

```
$ make verify
uv run ruff check .
All checks passed!
uv run ruff format --check .
163 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 149 source files
uv run lint-imports --no-cache
---------
Contracts
---------
Analyzed 192 files, 589 dependencies.
-------------------------------------
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
uv run pytest
........................................................................ [ 34%]
........................................................................ [ 69%]
...............................................................          [100%]
207 passed, 26 warnings in 3.98s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
✓ 105 modules transformed.
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-LZ_wtuT6.css    4.33 kB │ gzip:  1.44 kB
dist/assets/index-DnROQOsu.js   308.69 kB │ gzip: 96.25 kB │ map: 1,303.31 kB
✓ built in 2.34s
```

207 = the 199-test baseline + 8 new tests in `services/api/cadgpt/apps/review/tests/
test_rule_pack_selection.py` (multi-pack execution against the real engine, unknown/ambiguous
refusal, mutual exclusion with an uploaded rule set, reproducibility across a catalogue
mutation, tenancy). `make e2e` (real chromium, T-0024 harness) also reran green after these
changes — 1 passed — proving the existing single-`RuleSet` browser path is genuinely unchanged:

```
$ pnpm run e2e
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (13.8s)
  1 passed (15.1s)
```

### Real path, against `make up`'s running stack

Two tenants registered and provisioned for real (`t0031-atelier-a`, `t0031-atelier-b`), a real
`three_doors.ifc` uploaded, the catalogue already seeded with the three fixture packs from
T-0030 (`Accessible door width`, `Door name recorded`, `No doors permitted`, all `sample`/`0.1`).

**1. A real HTTP request creating a run with a catalogue selection, and the run record showing
exactly which packs and versions it cites.**

A review created with no `rule_set` (catalogue path):

```
$ curl -s -X POST http://localhost:8000/api/v1/reviews/ -H "Authorization: Bearer $TOKEN_A" \
    -H "X-Tenant: t0031-atelier-a" -d '{"name":"T0031 catalogue review 2","model_file":"'"$MODEL_UUID"'"}'
{"uuid":"066c805f-...","name":"T0031 catalogue review 2","model_file":{...},"rule_set":null,
 "latest_run":null,"created_at":"2026-09-02T22:10:51.073629Z", "...": "..."}
```

Checked with two packs selected:

```
$ curl -s -X POST http://localhost:8000/api/v1/reviews/066c805f.../check/ \
    -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0031-atelier-a" \
    -d '{"rule_packs":["cc0b0297-0ffb-4f6e-b4a1-4b538ece6457","93d79ffa-cf3e-47c9-a05d-90a6791db0c1"]}'
{"uuid":"c558c5e0-038e-4e57-90a5-07c46907a497","status":"pending", "...": "..."}
```

The run record, fetched immediately (before the worker touched it — the selection is already
there, captured at dispatch, not at execution):

```json
"rule_pack_selection": [
  {"name": "Accessible door width", "uuid": "cc0b0297-0ffb-4f6e-b4a1-4b538ece6457",
   "region": "", "version": "0.1", "jurisdiction": "sample",
   "checksum_sha256": "b4dc2920c4f2d240c9ce642e1e1bb8f4c331bb1860ddca9f0022004d557d692e",
   "specification_count": 1},
  {"name": "Door name recorded", "uuid": "93d79ffa-cf3e-47c9-a05d-90a6791db0c1",
   "region": "", "version": "0.1", "jurisdiction": "sample",
   "checksum_sha256": "7dc3d4f79abcb90baebbf5abb9a65bed4b92cb4bc4358b6ef80a9ad56ef5742d",
   "specification_count": 1}
]
```

**2. The check actually executing against those rules — worker log line plus resulting counts.** *(Corrected in the fix-now round below: the log line pasted here originally proved only that the citation was echoed back, not that those rules were what ran. See "Fix-now round" for F2's fix and the corrected claim.)*

```
worker-1 | ... check_run_pack_evaluated jurisdiction=sample name='Accessible door width'
           rule_pack_id=cc0b0297-0ffb-4f6e-b4a1-4b538ece6457 run_id=c558c5e0-...
           specifications_failed=1 specifications_indeterminate=0 specifications_passed=0
worker-1 | ... check_run_pack_evaluated jurisdiction=sample name='Door name recorded'
           rule_pack_id=93d79ffa-cf3e-47c9-a05d-90a6791db0c1 run_id=c558c5e0-...
           specifications_failed=0 specifications_indeterminate=0 specifications_passed=1
worker-1 | ... check_run_succeeded duration_seconds=0.805861 failed=1 indeterminate=1
           outcome=FAIL passed=4 run_id=c558c5e0-... tenant_id=3e5160db-...
```

The run afterward, `GET .../runs/c558c5e0.../`:

```json
{
  "status": "succeeded", "outcome": "FAIL", "engine_version": "0.1.0",
  "specifications_passed": 1, "specifications_failed": 1, "specifications_indeterminate": 0,
  "passed": 4, "failed": 1, "indeterminate": 1,
  "report": {
    "ids_title": "Accessible door width; Door name recorded",
    "specifications": [
      {"name": "Minimum clear door width 900 mm", "status": "FAIL", "passed": 1, "failed": 1,
       "indeterminate": 1, "...": "1 fail (800mm door), 1 indeterminate (no width), 1 pass"},
      {"name": "Door name recorded", "status": "PASS", "passed": 3, "failed": 0,
       "indeterminate": 0, "...": "all 3 doors have a Name"}
    ]
  }
}
```

2 specifications total (1 per pack, both evaluated something) — the coverage sentence "2 of 2
specifications ... evaluated" is exact across the whole selection, not reset per pack. Entity
counts sum correctly across packs: passed 1+3=4, failed 1+0=1, indeterminate 1+0=1 — matching
the header block above exactly.

**What this originally did *not* prove, corrected by F2 below:** the log line above was built entirely from `entry[...]` — the citation itself — so it could only ever agree with the citation; it could never have shown a mismatch even if one existed. The counts matching is real evidence (they come from the actual engine run), but the log line was not. See "Fix-now round".

**3. A refused selection — unknown and ambiguous, both named, neither silently dropped.**

```
$ curl -s -X POST http://localhost:8000/api/v1/reviews/<uuid>/check/ ... \
    -d '{"rule_packs":["cc0b0297-...","00000000-0000-0000-0000-000000000000"]}'
{"code":"validation_error","detail":"Unknown rule pack: 00000000-0000-0000-0000-000000000000."}
HTTP 400

$ curl -s -X POST .../check/ ... -d '{"rule_packs":["cc0b0297-...","cc0b0297-..."]}'
{"code":"validation_error","detail":"The same rule pack was selected more than once, which is
 ambiguous: cc0b0297-0ffb-4f6e-b4a1-4b538ece6457."}
HTTP 400

$ curl -s -X POST .../check/ ...   # no rule_packs, review has no rule_set
{"code":"validation_error","detail":"This review has no uploaded rule set. Select at least
 one rule pack from the catalogue to check against."}
HTTP 400
```

No `CheckRun` row was created by any of the three (checked via the DB in the corresponding
`pytest` tests: `test_an_unknown_pack_is_refused_not_silently_dropped`,
`test_the_same_pack_selected_twice_is_refused_as_ambiguous`,
`test_a_catalogue_review_refuses_a_check_with_no_selection`).

Localization proven over real HTTP, not just asserted: the same unknown-pack request with
`Accept-Language: fa` —

```
$ curl -s -X POST .../check/ -H "Accept-Language: fa" -d '{"rule_packs":["00000000-...-000000000000"]}'
{"detail":"بستهٔ مقرراتی ناشناخته: 00000000-0000-0000-0000-000000000000."}
```

**4. Reproducibility — the catalogue mutated after a run, the run's own citation unaffected.** *(Corrected in the fix-now round below: this item proves only the additive case, a new pack row, which an FK-based citation would survive identically. See "Fix-now round" for the same-uuid-different-bytes case this task actually needed and F1's enforcement of it.)*

The catalogue gains a version-bumped pack (a new row — T-0030's seeder never overwrites):

```
$ docker compose exec api python manage.py shell -c "
    RulePackService().seed(ids_path=.../door_width.ids, jurisdiction='sample', region='',
                            version='0.2', source_citation='...')"
created 36574c02-860c-4117-8a55-5747a7cda001 0.2
```

Catalogue now has 4 packs (both `0.1` and `0.2` of "Accessible door width"). The already
-completed run from item 2, re-fetched:

```json
"rule_pack_selection": [
  {"name": "Accessible door width", "uuid": "cc0b0297-0ffb-4f6e-b4a1-4b538ece6457",
   "version": "0.1", "checksum_sha256": "b4dc2920c4f2d240c9ce642e1e1bb8f4c331bb1860ddca9f0022004d557d692e", "...": "..."},
  {"name": "Door name recorded", "uuid": "93d79ffa-cf3e-47c9-a05d-90a6791db0c1",
   "version": "0.1", "...": "..."}
]
```

Byte-identical to item 1: still cites `0.1`, not the new `0.2` row, and `status`/`outcome` are
still `succeeded`/`FAIL` exactly as they finished.

**What this does *not* prove, corrected by F3 below:** a new row at a bumped version is an *additive* catalogue edit. A plain `ForeignKey(RulePack)` citation would survive it identically, because the old row is untouched — this item alone does not show the JSON snapshot is doing anything an FK could not also do. The edit that actually distinguishes them is the same uuid with different bytes behind it, which is exactly what F1's checksum verification now catches. See "Fix-now round".

**5. Tenancy — a run's selection visible to its own tenant, not to another.**

```
$ curl .../reviews/066c805f.../runs/c558c5e0.../ -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0031-atelier-a"
HTTP 200   rule_pack_selection present: True

$ curl .../reviews/066c805f.../runs/c558c5e0.../ -H "Authorization: Bearer $TOKEN_B" -H "X-Tenant: t0031-atelier-b"
HTTP 404   {"code":"not_found","detail":"The requested resource does not exist."}

$ curl .../reviews/ -H "Authorization: Bearer $TOKEN_B" -H "X-Tenant: t0031-atelier-b"
count: 0
```

Tenant B — a different owner, a different tenant, registered independently — gets 404 on the
run and an empty review list; the catalogue rows it selected from remain readable by both
(T-0030's global-catalogue guarantee, untouched).

**6. Wiring.**

Migration at head:

```
$ docker compose exec api python manage.py showmigrations review rulepack
review
 [X] 0001_initial
 [X] 0002_checkrun_rule_pack_selection_alter_review_rule_set
rulepack
 [X] 0001_initial
 [X] 0002_rulepack
```

Route, quoted from `services/api/cadgpt/apps/review/api/v1/urls.py` (the `check` action is
registered onto it by DRF's router reading the `@action` decorator on `ReviewViewSet.check`,
`services/api/cadgpt/apps/review/api/v1/views.py`):

```python
router = ScopedRouter(scope="tenant")
router.register("reviews", ReviewViewSet, basename="review")
...
@action(detail=True, methods=["post"], throttle_classes=[])
def check(self, request: Request, uuid: str) -> Response:
    ...
    serializer = self.get_serializer(
        data=request.data, context={**self.get_serializer_context(), "review": review}
    )
```

Serializer fields carrying the selection, `services/api/cadgpt/apps/review/api/v1/serializers.py`:

```python
class CheckRequestSerializer(serializers.Serializer[Any]):
    rule_packs = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    ...

class CheckRunDetailSerializer(CheckRunSummarySerializer):
    class Meta(CheckRunSummarySerializer.Meta):
        fields: tuple[str, ...] = (
            *CheckRunSummarySerializer.Meta.fields,
            "report", "model_checksum", "rule_set_checksum", "rule_pack_selection",
        )
```

### i18n — both catalogues

Backend (`services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`): four new `msgid`/`msgstr`
pairs for the four refusal/wiring messages `ReviewService._resolve_selection` raises, compiled
inside the `api` image (`compilemessages` runs at Docker build time) and verified live above
(item 3, `Accept-Language: fa`). Frontend (`services/web/src/i18n/en.json` and `fa.json`):
`review.ruleSetNone`, `review.catalogue.*` (picker labels), `report.selection.title` — every
new user-facing string in `ReviewsPage.tsx` and `ReportView.tsx` goes through `t(...)`, none
hardcoded.

### Layering

`packages/engine` has **zero changes** (`git status --porcelain` shows nothing under
`packages/engine/`) — `run_check` still takes exactly one `ids_path`; the several-packs case is
several calls from the service layer, never a new engine parameter. `uv run lint-imports
--no-cache` keeps all 5 contracts, including "The engine knows nothing about the service that
hosts it" — `RulePack` is imported by `review/services/execution.py` and `review/services/
review.py`, never by anything under `packages/engine`.

### What was not asked and was not built

Nothing scoped was left out. Selection is UUID-based (the frontend's jurisdiction/region/version
filters narrow which packs are *shown* to pick from; the actual request always names exact
UUIDs, so "ambiguous" is the duplicate-selection case named above, not a partial natural-key
lookup — a narrower and more defensible reading of the task's wording than adding a second,
partial-match selection syntax nothing else in the product uses). `RuleSet.tenant` remains
untouched and non-nullable; only `Review.rule_set` became nullable, which is the minimum needed
for "a review with no rule set of its own" to exist at all.

### Fix-now round — the review's four findings

The review (below) cleared tenancy, the lock narrowing, the three-valued combination, and the
`base/files.py` refactor. It found four defects in the recording itself, all fixed here, same
task, same builder, no second review.

**F1 — the citation recorded a checksum nothing ever read.** `CheckRunExecutor._evaluate_selection`
now recomputes each cited pack's checksum at execution time
(`RulePackService.checksum_of`, the one hashing primitive `snapshot` also uses) and compares it
against `entry["checksum_sha256"]` before evaluating anything. A mismatch raises a new
`RulePackCitationMismatchError`, caught in `execute()` and mapped to a new failure reason,
`CheckRunFailure.RULE_PACK_MODIFIED` (`services/api/cadgpt/apps/review/choices.py`) — distinct
from `INVALID_RULE_SET` because the file parses fine; it is simply not the file that was cited.
Both i18n catalogues carry the new label: the English source string and a new `fa` entry in
`services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`, compiled and verified live below.

Real path, against the running `make up` stack, not a unit test: `docker compose stop worker`;
`POST /reviews/{uuid}/check/` selecting the "No doors permitted" pack (`e92e8690-...`) — creates
a `PENDING` `CheckRun` and queues the Celery message, untouched, because no worker is running to
consume it; the pack's on-disk IDS file is then overwritten in place, same path, same uuid, with
`door_name_recorded.ids`'s bytes (`sha256` goes from `5574ea36...` to `7dc3d4f7...`); `docker
compose start worker` lets the queued message through:

```
$ curl -s http://localhost:8000/api/v1/reviews/e9d4c564.../runs/8e8a67c9.../     -H "Authorization: Bearer $TOKEN_A" -H "X-Tenant: t0031-atelier-a"
{
  "status": "failed",
  "failure_reason": "rule_pack_modified",
  "failure_detail": "Rule pack e92e8690-7d9a-4a28-8e54-ee129dee4885 (No doors permitted) was
   cited with checksum 5574ea369932f1d1c699f1daf2437b60e51fb2991e71c035d1b9c414588c56a9 at
   dispatch, but its file now hashes to 7dc3d4f79abcb90baebbf5abb9a65bed4b92cb4bc4358b6ef80a9ad
   56ef5742d. Refusing to evaluate a rule this run did not actually cite.",
  "report": null,
  "rule_pack_selection": [{"uuid": "e92e8690-...", "name": "No doors permitted",
    "checksum_sha256": "5574ea36...", "...": "..."}]
}
```

Worker log, same run:

```
worker-1 | ... check_run_failed detail='Rule pack e92e8690-... (No doors permitted) was cited
           with checksum 5574ea36... at dispatch, but its file now hashes to 7dc'
           reason=rule_pack_modified run_id=8e8a67c9-... service=CheckRunExecutor
```

`report` is `null` — the run refused outright, it did not evaluate the swapped bytes and report
on them as though they were what was cited, and it did not fall back to the originally-cited
content either (there is no "originally-cited content" to fall back to; the checksum is the only
record, and it disagreed). The pack's bytes were restored to the original afterward and the
restored checksum re-verified (`5574ea36...` again) so the catalogue is left honest for anything
that reuses this stack.

**F2 — the log line now proves what it claims.** `check_run_pack_evaluated` logs the cited
identity (`cited_name`, `cited_jurisdiction`, `cited_version`, `cited_checksum`, all from
`entry[...]`) *beside* what the produced report actually calls itself
(`evaluated_ids_title`, `evaluated_specification_names`, both from `report`, the real
`cadgpt_engine.Report` the engine just returned) — so the two can disagree. Item 2 above is
corrected in place: the original log line could only ever agree with the citation and did not
prove the check ran against those rules; this one can catch exactly the drift F1 now refuses.
Confirmed working against the real engine (`services/api/cadgpt/apps/review/tests/
test_rule_pack_selection.py::test_the_check_actually_executes_against_every_selected_pack`,
still green) — `evaluated_ids_title` and `evaluated_specification_names` come back matching the
citation whenever the bytes have not been tampered with, and F1's real-path run above shows the
same log line's sibling event (`check_run_failed`) firing instead of a false `check_run_pack_evaluated`
when they do not.

**F3 — the reproducibility test now proves the actual differentiator.** The original
`test_a_completed_run_still_reports_what_it_checked_after_the_catalogue_changes` is kept — it is
real and correct, but its docstring is corrected to say plainly what it does and does not show:
a new pack row (an *additive* edit) leaves an old run's citation untouched, which a plain
`ForeignKey(RulePack)` would do identically. Item 4 above is corrected in place with the same
admission. The differentiator is a new test,
`test_a_cited_packs_bytes_changing_behind_its_uuid_is_refused`: same uuid, bytes swapped in
storage directly (no in-repo path can do this — packs are immutable once seeded, T-0030 — so the
test does what F1's review did, and simulates the edit by hand), and asserts the run refuses with
`CheckRunFailure.RULE_PACK_MODIFIED` rather than silently evaluating whatever is there now. Green
in `make verify`'s 208.

**F4 — the coverage sentence no longer names a rule set that may not exist.**
`report.coverage.evaluated` in both `services/web/src/i18n/en.json` and `fa.json` changed from
*"{{evaluated}} of {{total}} specifications **in this rule set** were evaluated."* to
*"{{evaluated}} of {{total}} specifications were evaluated."* — true for both the
uploaded-rule-set path and a multi-pack catalogue selection, which is what the task's "one thing
to get right" asked for. `services/web/e2e/report.spec.ts`'s hardcoded assertion of the old
sentence was updated to match, and `make e2e` reran green against the rebuilt stack (1 passed),
proving the corrected copy actually renders in the browser, not just in the JSON catalogue.

**Re-verified after the fix-now round:**

```
$ make verify
... (unchanged commands)
uv run pytest
208 passed, 26 warnings in 4.29s   # was 207; +1 for F3's new test
Contracts: 5 kept, 0 broken.
cd services/web && pnpm run verify  # lint, typecheck, build all green
$ pnpm run e2e
  ✓  1 [chromium] › e2e/report.spec.ts ... (13.6s)
  1 passed (15.4s)
```

`docker compose -f deploy/compose.yaml up -d --build` rebuilt `api`/`worker`/`web` with the fix;
`showmigrations` still shows both apps at head (unchanged by this round — no model or migration
changed); the `fa` translation for the new `CheckRunFailure` label was verified compiled and
live in the running container (`gettext("A cited rule pack no longer matches the bytes this run
recorded")` under `translation.activate('fa')` returns the Persian string pasted above F1).

## Review

**Reviewed 2026-09-03. Verdict: four fix-now findings, all closed in this task; nine queued as
T-0045 through T-0050.** Gated on tenancy, and the review's own hunt list was pointed at what the
task claims to establish — the *recording* — rather than at the most intricate surface. That was
the right call twice over: the intricate surfaces held and the recording did not.

**Cleared under attack, not by sampling.** Tenancy: every read of the now-nullable `rule_set` is
null-guarded, `ReviewCreateSerializer` still resolves both `model_file` and `rule_set` through
`for_tenant`, the selection path touches only the global `RulePack`, and `ReviewViewSet` has no
update mixin so `rule_set` cannot be repointed after creation. The narrowed
`select_for_update(of=("self",))` opens no race — it is the only `select_for_update` in the
codebase, so nothing relied on the incidental locks the full-row form happened to take, and the
mutual exclusion idempotency depends on is still the `check_run` row. `_status_from_counts` is
line-for-line identical to the engine's private `_aggregate`, all-zero fallback included, and no
count merges the three buckets. A pack deleted between dispatch and execution fails loudly rather
than narrowing; a zero-specification pack cannot be seeded at all.

**The defect was that the citation was recorded and never read.** `checksum_sha256` was written by
`RulePackService.snapshot` and read by nothing — the reviewer executed the consequence: swap the
bytes behind a cited uuid between dispatch and execution and the run *succeeds*, flips `FAIL` to
`PASS`, and stores a citation naming a pack and a hash it did not check. No in-repo path can
mutate a seeded pack's bytes today, so it was not exploitable through the product; the defect is
that the guarantee rested on a docstring while the one column that could enforce it was inert.
`docs/decisions.md` had already named the reopening condition — *"the stored checksum the only
thing still telling the truth about what a run checked"* — and it would not have reopened,
because nothing read it. Now `_evaluate_selection` recomputes each pack's checksum at execution
and refuses with a new `CheckRunFailure.RULE_PACK_MODIFIED` rather than evaluating bytes the run
did not cite.

**Two evidence items claimed proof they could not deliver, and this is the more instructive half.**
The `check_run_pack_evaluated` log line built `name`, `jurisdiction` and `version` from the
citation, so it could only ever agree with the citation — it was the selection JSON echoed back
and pasted as proof the check ran against those rules. It now logs the produced report's own
`ids_title` and specification names beside the cited identity, so the line *can* disagree. And the
reproducibility test mutated the catalogue by seeding a **new row** at `0.2`, which a plain
`ForeignKey` would pass identically; it established nothing about the snapshot-versus-FK choice it
existed to justify. The only edit that distinguishes them is same-uuid-different-bytes — the exact
case nothing tested and nothing verified. `test_a_cited_packs_bytes_changing_behind_its_uuid_is_refused`
now covers it, and the additive test's docstring says honestly what it does and does not prove.

Fourth: the coverage sentence still read *"in this rule set"*, naming one rule set that does not
exist for a catalogue run. The count was right across the selection; the wording was not. Fixed in
both catalogues, with the e2e assertion and screenshot updated.

**Verified by the coordinator, not taken on trust.** `make verify` green — 208 tests (207 + 1 for
the new case), 5 import contracts kept, `mypy --strict` over 149 files; `makemigrations --check`
reports no changes; `packages/engine` has a zero-byte diff; the 10 structural tenant-isolation
tests pass. Three mutations were re-run independently and every one reproduced: taking
`_combine_reports`' specifications from the last pack only fails
`test_the_check_actually_executes_against_every_selected_pack`; removing the unknown-pack refusal
fails `test_an_unknown_pack_is_refused_not_silently_dropped`; and disabling the new checksum
comparison fails `test_a_cited_packs_bytes_changing_behind_its_uuid_is_refused` while the F2 log
line prints `cited_name: "Accessible door width"` beside `evaluated_ids_title: "Door name
recorded"` over an outcome of `PASS` — the review's scenario, now visible in the log that used to
conceal it.

**Queued, not fixed here:** T-0045 (the picker fetches one 20-row page and filters it client-side,
so a pack on page 2 reads as "no packs match this filter"), T-0046 (`services/web` has no test
runner at all despite being called RTL-native; the picker has never been rendered, and two
defects wait in it), T-0047 (`base/files.py` is typed `Any` at a new shared module boundary),
T-0048 (a failed run shows the tenant `list index out of range` and internal storage keys, and
never shows what it was supposed to check), T-0049 (no finding carries the pack identity that
produced it, which `prd.md` §5.7 requires and which is what would make `source_citation`
reachable), T-0050 (the sqlite test backend cannot see the Postgres-only defect class this task
itself hit).
