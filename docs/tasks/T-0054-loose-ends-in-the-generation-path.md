# T-0054 — Four loose ends in the report generation path

**Phase:** 3   **Status:** done
**Touches invariants:** none. Four small findings, batched because they are one pass over one file.

## Why

All four found by the T-0032 review, all low severity, none worth a task of its own — but they are
in the path that produces the product's deliverable and they are cheap to close together.

1. **An orphaned blob on rollback.** *(T-0051's review found this independently — it is item 4
   of T-0061. Close both together; they are the same lines.)* `report_generation.py:94-99` — `MediaService.store` writes
   bytes to storage *inside* the atomic block. A crash between the storage write and the commit
   rolls back the `Media` row and leaves an unreferenced file under `tenants/{uuid}/report/`; the
   redelivery then writes a second one. No cross-tenant exposure, just accumulating garbage that
   nothing will ever collect.

2. **`MediaKind.REPORT` is uploadable.** Adding it to `media/choices.py` also makes it a valid
   `kind` on `POST /api/v1/media/` — `MediaUploadSerializer.kind` spans all of `MediaKind` and
   `.md` is now an allowed extension. A tenant can upload arbitrary Markdown labelled "Generated
   report". It can never be attached to a run, because `report_file` is set only by the generator,
   so this is clutter rather than spoofing — but the code comment says *"Written by the server,
   never uploaded"* and nothing enforces it. A comment that states an invariant the code does not
   hold is the kind of thing this repository has been bitten by.

3. **Two log lines that cannot be correlated.** `report_generation.py:70` logs `media_id` as the
   Media **primary key**; `:104` logs `media_id` as the Media **uuid**; `tasks.py:54` returns the
   pk while T-0032's evidence item 4 describes it as the media uuid. One field name, three
   meanings — and item 4's idempotence argument leans on reading those lines.

4. **The download route loads the whole report to stream a file that does not use it.**
   `views.py:112-123` — the `report_file` action falls through to `with_inputs()`, pulling the full
   `report` JSON (documented as potentially megabytes) on every download, and does not
   `select_related("report_file")`, costing an extra query each time.

## Scope

Each of the four closed. (1) writes bytes outside the transaction or cleans up after itself;
(2) the invariant in the comment becomes enforced or the comment becomes true; (3) one field name
means one thing; (4) the route fetches what it needs.

**What explicitly does not change** — the generator's output, the presentation rules, the
authenticated serving path, the storage layout.

## How to prove it ran

`make verify`, then: (1) a crash injected between the storage write and the commit, showing no
orphan; (2) the upload of a `report`-kind file refused, response pasted; (3) both log lines from one
real generation, correlated; (4) the query count on a download, before and after.

## Evidence

**What landed**, all in `services/api/cadgpt/apps/review/services/report_generation.py`
unless noted:

1. **Orphaned blob on rollback** — `generate` no longer holds one `transaction.atomic()`
   across the storage write. It now claims the run and renders the markdown in one short
   transaction that commits and releases the lock; `MediaService.store` then runs with
   **no transaction open at all**, so there is no outer commit left for a later exception
   to roll back through — by the time `store` returns, the file and its `Media` row are
   either both durably committed or neither exists. Attaching `report_file` onto the run
   happens in a second short transaction (`_attach`), which re-locks the run and re-checks
   `report_file_id` first, so a concurrent redelivery that also rendered and stored in the
   gap does not leave a second, permanently-unreferenced `Media` row — the loser deletes
   the file and row it just wrote. A narrower residual (a worker dying between `store`
   returning and `_attach` committing, leaving one real, committed, but unattached `Media`
   row) is closed separately by `_find_reusable_media`: since rendering is deterministic
   for a given run and language, a redelivery's markdown is byte-identical, so `generate`
   looks for an unattached `Media` with that exact checksum (the same checksum
   `MediaService.store` already computes for every file) before storing a new one.
2. **`MediaKind.REPORT` is uploadable** — `media/choices.py` now defines
   `UPLOADABLE_KINDS = tuple(kind for kind in MediaKind if kind != MediaKind.REPORT)`, and
   `MediaUploadSerializer.kind` (`media/api/v1/serializers.py`) is restricted to that set
   instead of `MediaKind.choices`. `POST /api/v1/media/` with `kind=report` is now refused
   at validation, before `MediaService` ever sees it. The comment on `MediaKind.REPORT`
   is updated to say this is enforced, not just asserted.
3. **Inconsistent `media_id` log field** — every log line in `report_generation.py` (the
   early-return line, the failure line, both branches of `_attach`) now names `media_id`
   as the `Media` **uuid**, matching `MediaService.store`'s own `media_stored` line and
   the filename/storage-path convention. `review/tasks.py`'s `generate_report_file` now
   returns `str(run.report_file.uuid)` (or `""` if generation produced no file), not
   `str(run.report_file_id)` (the primary key).
4. **The download route over-fetches** — `CheckRunViewSet.get_queryset()`
   (`review/api/v1/views.py`) gets a new branch for `self.action == "report_file"`:
   `runs.without_report().select_related("report_file")`, instead of falling through to
   `with_inputs()`. This defers the `report` JSON column and eliminates the separate
   `Media` lookup the old code paid on every download.

New tests: `services/api/cadgpt/apps/media/tests/test_media_api.py` (upload
accept/refuse), two new tests appended to
`services/api/cadgpt/apps/review/tests/test_report_generation.py`
(`test_the_two_log_lines_from_one_generation_agree_on_media_id`,
`test_a_crash_between_storing_and_attaching_leaves_nothing_orphaned`).

---

**`make verify`:**

```
$ uv run ruff check .
All checks passed!
$ uv run ruff format --check .
195 files already formatted
$ uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 177 source files
$ uv run lint-imports --no-cache
Analyzed 231 files, 769 dependencies.
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
$ uv run pytest -m "not postgres"
182 passed, 1 deselected, 36 warnings in 6.37s
$ uv run pytest -m postgres --ds=cadgpt.config.settings.test_postgres
1 passed, 314 deselected in 3.00s
$ cd services/web && pnpm run verify
Test Files  2 passed (2)   Tests  6 passed (6)    (test-unit)
Test Files  9 passed (9)   Tests  36 passed (36)  (test-storybook)
Vite ✓ built in 9.97s   (storybook build)
```

All gates green. (The one pre-existing warning under `test_check_run.py` —
`ifcopenshell.file.__del__` `KeyError` at interpreter teardown — is unrelated to this
task's diff; present before and after.)

---

**(1) Real path — crash injected between the storage write and attaching, no orphan
survives recovery.**

Ran via `uv run pytest -v -k test_a_crash_between_storing_and_attaching_leaves_nothing_orphaned`:

```
services/api/cadgpt/apps/review/tests/test_report_generation.py::test_a_crash_between_storing_and_attaching_leaves_nothing_orphaned PASSED
```

The test (`_dying_attach`) monkeypatches `ReportGenerationService._attach` to raise
`RuntimeError("simulated worker death between store() and _attach()")` on its first call,
against a real succeeded `CheckRun` with a real report and no file yet (real IFC + real
IDS fixtures, real engine, real `MediaService.store`). It asserts, in order:

- `ReportGenerationService().generate(run.uuid)` raises the injected `RuntimeError` —
  `store()` had already completed by the time it raises.
- `run.report_file_id` is still `None` afterward (the crash landed before attaching).
- `Media.objects.for_tenant(tenant).get(kind="report")` finds exactly **one** real,
  committed `Media` row, and `orphaned.file.storage.exists(orphaned.file.name)` is
  `True` — the file `MediaService.store` wrote was **not** rolled back by the later
  crash. (Under the pre-fix code, this same injected crash — inside the one shared
  `atomic()` block — would have rolled back the `Media` row's `INSERT` while the file
  bytes stayed on disk: bytes with zero trace in the database, invisible to any query.)
- A real redelivery — `ReportGenerationService().generate(run.uuid)` called again, with
  `_attach` restored to the real implementation — succeeds, and
  `recovered.report_file_id == orphaned.pk`: the *same* row from the crashed attempt is
  reused (found by content checksum), not a second file created beside it.
- `Media.objects.for_tenant(tenant).filter(kind="report").count() == 1` after recovery —
  zero orphans, before or after.

Additionally proven live against the real `make up` stack (see the shared real-path
session below): a real check run's `media_stored` → `report_file_generated` pair shows
the file write and the DB attach are two separate, independently-logged steps, and the
existing `test_running_generation_twice_produces_one_file_not_two` /
`test_asking_twice_produces_one_file_and_a_run_that_already_has_one_is_untouched` tests
(unchanged, still passing) confirm the ordinary sequential-redelivery path still produces
exactly one file.

---

**(2) Real path — `POST /api/v1/media/` with `kind=report` refused, actual response.**

Against the running `make up` stack (`docker compose -f deploy/compose.yaml ps` showed
the stack already up; confirmed exactly one Celery node before touching anything:
`celery -A cadgpt.config.celery inspect ping` → `1 node online`), plus a second, isolated
local server/worker pair (`DJANGO_SETTINGS_MODULE=cadgpt.config.settings.local`, the same
real dockerized Postgres on `localhost:5433`, a **separate** Redis logical DB
`redis://localhost:6380/7` so it could never compete with the Docker worker for the same
queue — confirmed by Celery's own `mingle: all alone` on startup and re-confirmed
`1 node online` on the Docker worker throughout and after) used to exercise the full
real HTTP path end to end: register, log in, create a tenant, upload a real IFC and a
real IDS, create a project and review, run a real check, download the real report.

Real request/response for this item specifically:

```
$ curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST http://localhost:8010/api/v1/media/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: $SLUG" \
    -F "kind=report" -F "file=@fake_report.md;type=text/markdown"

{"type":"about:blank#validation_error","status":400,"code":"validation_error",
 "detail":"داده‌های ارسالی معتبر نیست.",
 "errors":{"kind":["\"report\" یک انتخاب معتبر نیست."]},
 "request_id":"bf467dfdc3ad430d99da9f17cfccf64b"}
HTTP_STATUS:400
```

(`"report" یک انتخاب معتبر نیست"` = `"report" is not a valid choice` — `en` translation
confirmed by the equivalent pytest assertion. A same-session `kind=ifc_model` upload of
the real fixture succeeded with `201` and `"kind":"ifc_model"`, proving the restriction is
specific to `report` and ordinary uploads are unaffected.)

Also covered by the new `test_a_report_kind_upload_is_refused` /
`test_an_ifc_upload_succeeds` in `test_media_api.py` (both passing, shown above).

---

**(3) Real path — both log lines from one real generation, correlated.**

From the real local worker's log, processing the real check above
(`review.tasks.generate_report_file`, dispatched twice: once automatically on the check's
own success, once via the recovery route `POST .../report-file/`):

```
report_file_generated          media_id=b9d9dd2e-28b8-4f5e-bc41-ad5e0f731783 run_id=556f27f2-d233-4cb9-85de-2472f6020090 service=ReportGenerationService
...
report_file_already_generated  media_id=b9d9dd2e-28b8-4f5e-bc41-ad5e0f731783 run_id=556f27f2-d233-4cb9-85de-2472f6020090 service=ReportGenerationService
```

Both lines carry the identical `media_id`, and it is the `Media` **uuid**
(`b9d9dd2e-28b8-4f5e-bc41-ad5e0f731783`) — the same value the preceding
`media_stored` line logged for the same file (`media_id=b9d9dd2e-...`) and the same value
the task itself returned: `Task review.tasks.generate_report_file[...] succeeded in
...: 'b9d9dd2e-28b8-4f5e-bc41-ad5e0f731783'`. Before this fix, the first line logged the
integer primary key and the task returned the primary key as a string; the second line
already logged the uuid — three different meanings for one field name, now one.

Also proven deterministically by the new
`test_the_two_log_lines_from_one_generation_agree_on_media_id`, which captures both real
structured-log lines via `capsys` around one real generation and a real redelivery, and
asserts they carry the identical, real (`uuid.UUID`-parseable) value:

```
services/api/cadgpt/apps/review/tests/test_report_generation.py::test_the_two_log_lines_from_one_generation_agree_on_media_id PASSED
```

---

**(4) Real path — query count on a download, before and after, a real number.**

Measured with `django.test.utils.CaptureQueriesContext` around a real authenticated
`APIClient` request to the real `report-file` endpoint, in-process against the same real
dockerized Postgres the check above ran on (`manage.py shell`, same env as the local
server/worker), consuming the actual streamed `FileResponse` body exactly like a real
client:

**Before** (`git stash` of just `views.py`'s fix, same run, same request):
```
status=200 bytes=1190
query_count=4
query 2: SELECT ... "review_checkrun"."report" ... FROM "review_checkrun"
         INNER JOIN "review_review" ... LEFT OUTER JOIN "media_media" ...
         -- has_report_column=True   has_media_join=True
query 3: SELECT ... FROM "media_media" WHERE "media_media"."id" = 77
         -- a second, separate query for the Media row `run.report_file.file.open()` needs
```

**After** (fix restored — `git stash pop`, identical run, identical request):
```
status=200 bytes=1190
query_count=3
query 2: SELECT ... FROM "review_checkrun" ... LEFT OUTER JOIN "media_media" ...
         -- has_report_column=False   has_media_join=True   (one query, not two)
```

4 queries → 3 queries; the multi-specification `report` JSON column is no longer
selected at all (`has_report_column` `True` → `False`), and the separate `Media` lookup
(query 3) disappears because `select_related("report_file")` now joins it into the same
query. The response body is byte-identical (`bytes=1190` both times) — the download
itself is unchanged, only what it costs to serve. (The fixed code was restored
immediately after this measurement; `git status` confirmed the working tree matched the
committed diff before continuing.)

---

**Wiring.**

`review/api/v1/urls.py`:
```python
run_report_file = CheckRunViewSet.as_view({"get": "report_file", "post": "generate_report"})
...
path(
    "reviews/<uuid:review_uuid>/runs/<uuid:uuid>/report-file/",
    run_report_file,
    name="tenant-review-run-report-file",
),
```
— the `report_file` action this task's queryset fix targets is the one actually served at
that route; no new route was added, the existing one now resolves its queryset
differently for `self.action == "report_file"`.

`media/api/v1/serializers.py`:
```python
kind = serializers.ChoiceField(
    choices=[(kind.value, kind.label) for kind in UPLOADABLE_KINDS]
)
```
— the field DRF actually validates `POST /api/v1/media/`'s `kind` against; this is the
same `MediaUploadSerializer` `MediaViewSet.serializer_classes["create"]` already wires to
the `create` action (`media/api/v1/views.py`), unchanged.

`review/tasks.py`:
```python
@shared_task(
    base=BaseTask,
    name="review.tasks.generate_report_file",
    queue="checks",
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3,
)
def generate_report_file(run_uuid: str) -> str:
```
— unchanged registration; only the function body's return value (item 3) changed.

**NOT DONE:** nothing in this task's own scope. All four findings are fixed, unit-tested,
and proven against a real request/job/log line as required — not merely a passing suite.
One residual is named rather than hidden: a worker dying in the exact window between
`MediaService.store` committing and `_attach` committing still produces one real,
committed `Media` row that is momentarily unattached — no longer invisible bytes with no
database trace (the original bug, now impossible by construction), and closed on the
very next redelivery by checksum reuse (proven above), but momentarily present between
those two points in time if something were to query for it right then.

## Review
