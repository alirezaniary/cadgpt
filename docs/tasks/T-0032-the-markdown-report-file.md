# T-0032 — The report as a file, and its URL on the job record

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** I7, three-valued results, tenancy. **Reviewer-gated.**

## Why

This is the MVP's last clause and the thing the whole loop has been building toward: *the user
uploads a model, picks which rules to run it against, and **gets back a report file**.*

Settled 2026-09-02 (`docs/decisions.md`, `prd.md` §12): the deliverable is a **generated
Markdown report** whose URL sits on the job record. Markdown because it survives the tooling,
renders where the office already works, and needs no layout engine. The in-app React view stays
**beside** it, not under it — this task does not replace the view and must not degrade it.

Everything this file has to say has already been built and reviewed. The file is not a new
report; it is the report we already produce, in the form that leaves the building:

- the **disclosure** (T-0029) — what was checked, the model and not the drawing set;
- **coverage before findings** (T-0025), with the numerator that is a real measurement and not
  `N of N`, and the specifications that established nothing named rather than counted;
- **severity ordering** FAIL → INDETERMINATE → PASS (T-0025);
- the **requirement as a localized citation** with its subject (T-0027);
- the three counts, all three, always (I3).

## The decision this task inherits

`docs/decisions.md`, *"Report prose belongs to the server, not to the frontend catalogue"* —
written because of this task. **Every string in the generated file is authored on the server**,
through `gettext`, and the disclosure specifically comes from `cadgpt.apps.review.disclosure`,
which already exists and which the React view already renders from. Do not retype a sentence
that module owns; do not build a second catalogue. If you find yourself needing a string the
server does not have, add it beside the existing ones rather than inlining it in a template.

The presentation rules `ReportView.tsx` implements are the **specification** for this generator
(`docs/plan.md`). Where the file and the view disagree about ordering, coverage arithmetic, or
what is named, the file is wrong.

## Scope

**Changes**

- A generator in `services/api/cadgpt/apps/review/` producing Markdown from a stored report.
  Business logic in a service. It takes the localized report — the same `localize_report` output
  the API serves — so wording and rendering stay one path, not two.
- The **language** of the file is a real decision: a run belongs to a tenant, the file is
  generated once, and Markdown carries no locale negotiation. Decide deliberately whose language
  the file is written in, implement it, and **state the choice and its reasoning in the
  evidence**. If it is the tenant's configured language, say what happens when that changes
  after the file was written.
- The file is stored through the existing `media` app rather than a new storage path, under the
  tenant's prefix, and its URL goes on the job record. **One tenant never sees another's file** —
  this is the tenancy invariant and it applies to a generated artifact exactly as to an upload.
- Generation is dispatched **on commit, never inside the transaction**, and the task is
  **idempotent** — `acks_late` means the message survives a dead worker and will be delivered
  again. Re-running must not produce a second file or a half-written one.
- `services/web` — surface the link on the run.
- Tests, including a real one that reads the generated file's bytes.

**What explicitly does not change**

- The engine, the report schema, the counts, the view. This task reads what exists.
- No PDF, no HTML export, no overlay, no marked sheets, no BCF — out of the MVP by decision.
- No new presentation rules. If the file needs a rule the view does not have, that is a finding
  about the view, not licence to invent one here.

## How to prove it ran

`make verify` with the 5 import contracts kept, then the real path end to end on the running
stack — upload, check, and fetch the file:

```sh
make up
# a real run, then GET the report URL off the job record
```

Evidence must show:

1. **The generated file itself, pasted whole**, for the `three_doors.ifc` / `door_width.ids` run.
   It must contain the disclosure, coverage before findings, the three counts, and the FAIL row
   ordered above the INDETERMINATE row. Paste the raw Markdown, not a rendering of it.
2. The same file **in the other language**, proving the wording came from the server's catalogue
   and not from a template's hardcoded English.
3. The URL on the job record, fetched over real HTTP, and the file downloaded from it.
4. **Idempotence**: run the generation task twice against the same run and show one file, not
   two — paste both invocations and the resulting file list.
5. **Tenancy**: a second tenant refused access to the first tenant's file. Paste the response.
6. **Wiring**: the Celery task registered (quote the registration), dispatch on commit (quote
   the line), the migration at head, and the route.
7. A mutation proof on the assertion that coverage precedes findings in the file.

## Evidence

**Revised after the T-0032 review.** Three fix-now findings (A1, A2, A3) are addressed below,
in the same evidence structure as before; corrected items are marked **[corrected]**. Findings
outside A1/A2/A3 were queued by the coordinator as T-0051 onward and are not addressed here.

**`make verify`**: all gates pass, all 5 import contracts kept, after the fixes.

```
uv run ruff check .          -> All checks passed!
uv run ruff format --check . -> 167 files already formatted
uv run mypy packages/engine/src services/api/cadgpt -> Success: no issues found in 153 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest                -> 228 passed, 29 warnings in 3.32s   (baseline 208 + 20 new)
cd services/web && pnpm run verify -> lint clean, tsc clean, vite build succeeded
```

`make e2e`:

```
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (9.3s)
  1 passed (10.2s)
```

**The language decision.** Unchanged from the first round: a generated file has no request
to negotiate a language from — Markdown carries no `Accept-Language`, and it is written
once. `Tenant.language` already existed for exactly this (its own docstring: *"Reports and
notifications are written in this language unless a member overrides it"*), so
`ReportGenerationService.generate` activates `run.tenant.language`
(`django.utils.translation.override`) for the one render, and both `localize_report` and
`render_markdown_report` run inside that context. **If the tenant's language changes after
generation, the stored file does not change** — it is bytes in storage, exactly like an
uploaded model.

---

### A1 — the on-commit test now actually distinguishes on-commit from inline dispatch

**Finding**: `test_dispatch_is_registered_on_commit_not_inside_the_transaction` captured
callbacks with `execute=False` and asserted on state that never depended on `execution.py`'s
own dispatch — `_succeed` was never reached, so the test passed identically whether the
dispatch was on-commit or an inline `.delay()`. The docstring's claim about "Django's
draining loop" running inside the capture was wrong: `execute=False` drains nothing.

**Fix**: rewrote the test (`services/api/cadgpt/apps/review/tests/test_report_generation.py`).
It now captures *only* the check's own dispatch without running it, invokes that one
callback by hand (still inside the test's real transaction, outside any capture context —
this runs `execute_check_run` through to `CheckRunExecutor._succeed`), and asserts
`report_file_id` is still `None` immediately afterward. If dispatch is on-commit, the
registration this makes just joins the connection's pending on-commit queue, undrained. If
dispatch were inline, it would already have run (`CELERY_TASK_ALWAYS_EAGER`) and
`report_file_id` would already be set.

**Mutation proof it is no longer hollow** — `execution.py:226`'s
`transaction.on_commit(lambda: generate_report_file.delay(str(run.uuid)))` was replaced with
a bare `generate_report_file.delay(str(run.uuid))`:

```
$ uv run pytest services/api/cadgpt/apps/review/tests/test_report_generation.py::test_dispatch_is_registered_on_commit_not_inside_the_transaction -q

FAILED test_report_generation.py::test_dispatch_is_registered_on_commit_not_inside_the_transaction
    assert run.report_file_id is None, (
        "report generation must still be queued on-commit, not already run inline"
    )
E   AssertionError: report generation must still be queued on-commit, not already run inline
E   assert 3 is None
E    +  where 3 = <CheckRun: Ground floor - succeeded>.report_file_id
```

Mutation reverted (`git diff` on `execution.py` shows only the legitimate on-commit line,
no leftover marker); `uv run pytest services/api/cadgpt/apps/review -q` clean afterward.

**Item 6, corrected** — see "Wiring" below: it now states plainly that the quoted line by
itself proves nothing, and points at this mutation as the actual proof.

### A2 — the Persian file now names every verdict exactly as the screen does **[corrected]**

**Finding**: the file's Persian catalogue used different words than
`services/web/src/i18n/fa.json` for the same three-valued verdicts and the indeterminate
note, and `msgid "Failed"` was shared, untagged, between a failed check *run*
(`CheckRunStatus.FAILED`) and a count of failing *findings* (the coverage header).

**Fix**:

- `cadgpt/apps/review/choices.py`'s `OutcomeStatus.FAIL` / `INDETERMINATE` `.po` entries
  changed to match `status.FAIL` / `status.INDETERMINATE` in `fa.json` exactly: `Fail` →
  `مردود` (was `رد`), `Indeterminate` → `نامشخص` (was `نامعلوم`). `PASS` already matched
  (`قبول`) and is unchanged.
- The coverage table headers changed to match `report.passed` / `report.indeterminate`
  exactly: `Passed` → `قبول` (was `موفق`), `Could not be determined` → `قابل تعیین نبود`
  (was `قابل تشخیص نبود`).
- The indeterminate note changed to match `report.indeterminateNote` word for word:
  `این موارد بررسی نشدند و قبول به شمار نمی‌آیند.` (was a different sentence).
- **`"Failed"` disambiguated.** `report_markdown.py`'s coverage-table `Failed` header now
  goes through `pgettext("report coverage table: count of failing findings", "Failed")`,
  giving it its own `msgctxt` entry in `django.po` (`مردود`, matching `report.failed`)
  entirely separate from the bare, context-free `_("Failed")` msgid `CheckRunStatus.FAILED`
  uses (still untranslated in `.po` — it has never been rendered anywhere in this product;
  confirmed below that the two no longer share one `.po` entry).

Confirmed live, inside the redeployed `api` container, in `fa`:

```
$ docker compose -f deploy/compose.yaml exec api python -c "
import django; django.setup()
from django.utils import translation
from django.utils.translation import gettext, pgettext
with translation.override('fa'):
    from cadgpt.apps.review.choices import OutcomeStatus
    print('Fail label (fa):', OutcomeStatus.FAIL.label)
    print('Indeterminate label (fa):', OutcomeStatus.INDETERMINATE.label)
    print('Passed header (fa):', gettext('Passed'))
    print('Failed header, plain (fa):', gettext('Failed'))
    print('Failed header, pgettext (fa):', pgettext('report coverage table: count of failing findings', 'Failed'))
    print('Could not be determined (fa):', gettext('Could not be determined'))
    print('Indeterminate note (fa):', gettext('These were not checked. They are not passes.'))
"
Fail label (fa): مردود
Indeterminate label (fa): نامشخص
Passed header (fa): قبول
Failed header, plain (fa): Failed
Failed header, pgettext (fa): مردود
Could not be determined (fa): قابل تعیین نبود
Indeterminate note (fa): این موارد بررسی نشدند و قبول به شمار نمی‌آیند.
```

The plain `gettext('Failed')` (what `CheckRunStatus.FAILED.label` would resolve to) stays
untranslated (`Failed`, the source string) — proof there is no longer a shared `.po` entry
between the two meanings; only the `pgettext`-scoped coverage-header lookup resolves to
`مردود`.

### 2. The same file in the other language — **regenerated, wording now matches the screen [corrected]**

Fresh run, same fixtures, `atelier-farsi` tenant (`"language": "fa"`), real HTTP round trip
against the redeployed stack:

```markdown
# Accessible door width

three_doors.ifc · شمای مدل IFC4 · موتور 0.1.0

**وضعیت:** مردود

## آنچه در این گزارش بررسی شد

این گزارش مدل three_doors.ifc را بررسی کرده است — نه مجموعه نقشه‌هایی که دفتر شما برای بازبینی ارائه می‌دهد. مدل و مجموعه نقشه‌های ارسالی می‌توانند با هم واگرا شوند: جزئیاتی که مستقیماً روی یک نما ترسیم شده، جدولی که دستی تایپ شده، جدول مساحت در کارتوش. هیچ‌یک از این واگرایی‌ها در اینجا بررسی نشده است. نتیجهٔ زیر مدل را توصیف می‌کند؛ دربارهٔ نقشه‌ها چیزی نمی‌گوید.

## پوشش

1 از 1 مشخصه بررسی شد.

| قبول | مردود | قابل تعیین نبود |
|---|---|---|
| 1 | 1 | 1 |

> این موارد بررسی نشدند و قبول به شمار نمی‌آیند.

## مشخصه‌ها

### Minimum clear door width 900 mm — مردود

3 عضو منطبق بودند · required

All IFCDOOR data

**OverallWidth باید دست‌کم 900 باشد.**

| وضعیت | کلاس IFC | شناسهٔ سراسری | دلیل | جزئیات |
|---|---|---|---|---|
| مردود | IfcDoor | 3worKcMPzD8x0Y1nJVBqA2 | مقدار ویژگی قاعده را برآورده نمی‌کند. | The attribute value "800.0" does not match the requirement |
| نامشخص | IfcDoor | 3worKcMPzD8x0Y1nJVBqA3 | ویژگی موجود است ولی مقداری ندارد. | The attribute value "None" is empty |
```

Cross-check against `services/web/src/i18n/fa.json`, word for word: `**وضعیت:** مردود`
(`status.FAIL` = `"مردود"`); the coverage row `قبول | مردود | قابل تعیین نبود`
(`report.passed` = `"قبول"`, `report.failed` = `"مردود"`, `report.indeterminate` =
`"قابل تعیین نبود"`); the indeterminate note (`report.indeterminateNote`, identical); the
findings table's `مردود` / `نامشخص` (`status.FAIL` / `status.INDETERMINATE`). The file and
the screen now name every verdict identically. What stays untranslated on purpose, exactly
matching `ReportView.tsx`'s own behaviour, is raw engine/IDS data the view never translates
either: the specification's own name (author's IDS text), `cardinality` (`required`), and
`entity.detail` (ifctester's own English sentence).

### 3. The URL on the job record, fetched over real HTTP, file downloaded

Unaffected by A1–A3; re-confirmed against the redeployed stack with the fresh run above:

```
$ curl -s http://localhost:8000/api/v1/reviews/$REVIEW/runs/$RUN/ -H "Authorization: Bearer $ACCESS" -H "X-Tenant: atelier-t0032"
"report_file_url": "/api/v1/reviews/388b0660-d269-4843-9818-3bdaaad0c4f9/runs/8c1e3de1-6d8b-44ed-aa84-a950874b3ad0/report-file/"

$ curl -s -D - -o /tmp/report_en2.md "http://localhost:8000$report_file_url" -H "Authorization: Bearer $ACCESS" -H "X-Tenant: atelier-t0032"
HTTP/1.1 200 OK
Content-Type: text/markdown
Content-Length: 1190
Content-Disposition: attachment; filename="report-8c1e3de1-6d8b-44ed-aa84-a950874b3ad0.md"
```

`cat /tmp/report_en2.md` reproduces item 1's content byte-for-byte (English wording did not
change in this round).

### 4. Idempotence: the generation task run twice against the same run, real stack, re-confirmed

```
$ docker compose -f deploy/compose.yaml exec -T api python manage.py shell -c "
from cadgpt.apps.review.models import CheckRun
from cadgpt.apps.media.models import Media
from cadgpt.apps.review.tasks import generate_report_file
run = CheckRun.objects.get(uuid='8c1e3de1-6d8b-44ed-aa84-a950874b3ad0')
print('report_file_id before:', run.report_file_id)
print('report-kind media rows before:', Media.objects.filter(tenant=run.tenant, kind='report').count())
result = generate_report_file(str(run.uuid))
print('second invocation returned media uuid:', result)
run.refresh_from_db()
print('report_file_id after:', run.report_file_id)
print('report-kind media rows after:', Media.objects.filter(tenant=run.tenant, kind='report').count())
"
report_file_id before: 152
report-kind media rows before: 3
{"event": "report_file_already_generated", "media_id": 152, "run_id": "8c1e3de1-...", "service": "ReportGenerationService"}
second invocation returned media uuid: 152
report_file_id after: 152
report-kind media rows after: 3
```

Same media id before and after, row count unchanged. Unit-level idempotence:
`test_running_generation_twice_produces_one_file_not_two`.

### 5. Tenancy: a second tenant refused, re-confirmed against the redeployed stack

```
$ curl -s -i "http://localhost:8000/api/v1/reviews/388b0660-d269-4843-9818-3bdaaad0c4f9/runs/8c1e3de1-6d8b-44ed-aa84-a950874b3ad0/report-file/" \
    -H "Authorization: Bearer $RIVAL_ACCESS" -H "X-Tenant: rival-co"
HTTP/1.1 404 Not Found
Content-Type: application/json
```

No storage URL was ever handed out to construct this request from — `report_file_url` is
the authenticated route, unlike `RulePackSerializer.source_file` (T-0042, queued).

### 6. Wiring — **item 6 corrected: a quoted line alone proves nothing; the mutation does**

The review is right that pasting the dispatch line by itself does not distinguish on-commit
from inline dispatch — that distinction is only established by the mutation proof under A1
above, which now exists and is reproducible. The other wiring facts stand as quoted facts,
not as proof of the on-commit property specifically:

**Celery task registered**, quoted from `services/api/cadgpt/apps/review/tasks.py`:

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

Confirmed live on the worker: `celery -A cadgpt.config.celery inspect registered` →
`* review.tasks.generate_report_file` (alongside `* review.tasks.execute_check_run`).

**Dispatch is on-commit** — proven, not merely quoted, by the A1 mutation above. The line
itself, for reference (`services/api/cadgpt/apps/review/services/execution.py`,
`CheckRunExecutor._succeed`):

```python
with transaction.atomic():
    run.status = CheckRunStatus.SUCCEEDED
    ...
    run.save()
    transaction.on_commit(lambda: generate_report_file.delay(str(run.uuid)))
```

**Migration at head**:

```
$ docker compose -f deploy/compose.yaml exec -T api python manage.py showmigrations review
review
 [X] 0001_initial
 [X] 0002_checkrun_rule_pack_selection_alter_review_rule_set
 [X] 0003_checkrun_report_file_alter_checkrun_failure_reason
```

**Route**, quoted from `services/api/cadgpt/apps/review/api/v1/urls.py`:

```python
run_report_file = CheckRunViewSet.as_view({"get": "report_file"})
...
path(
    "reviews/<uuid:review_uuid>/runs/<uuid:uuid>/report-file/",
    run_report_file,
    name="tenant-review-run-report-file",
),
```

### 7. Mutation proof: coverage precedes findings

Unchanged from the first round — still reproduces. Mutated
`services/api/cadgpt/apps/review/services/report_markdown.py` to emit `## Specifications`
before `## Coverage`, ran the two tests that assert the ordering (one unit test, one
real-HTTP integration test), both failed on the targeted assertion
(`assert body.index("## Coverage") < body.index("## Specifications")` →
`AssertionError: assert 503 < 484`), mutation reverted, full suite clean afterward.

### A3 — injected structure neutralized, proven on the real running stack

**Finding**: a specification `name` (or `applicability_description`, or the uploaded
model's filename via the disclosure) reaching the file unescaped could open a new Markdown
block — the reviewer's PoC rendered a second, fabricated `## Coverage` section claiming
`99 of 99 specifications were evaluated. Everything complies.`

**Fix**: `services/api/cadgpt/apps/review/services/report_markdown.py` adds
`_sanitize_text`, applied to every data-sourced string reaching the file outside a table
cell (`_escape_cell` already covered those): the title, the uploaded filename, the
disclosure title/text, rule-pack selection entries, specification names (both in the
findings list and the "established nothing" list), `cardinality`, `applicability_description`,
`reason_label`, and `requirement_text`. It collapses every embedded line break to a space —
the whole attack, since a Markdown block can only ever start at the beginning of a real
line — and, for the one field rendered as a bare paragraph with nothing server-written on
its own line first (`applicability_description`), prefixes a zero-width space if the
field's own first character would otherwise be read as a block starter.

**Real-stack proof, not just a unit test.** Built a real IDS file
(`packages/engine/tests/fixtures/door_width.ids` with the specification's `name` attribute
changed to the reviewer's exact injection string, using `&#10;` XML character references so
the parser preserves the newlines rather than normalizing them away) and ran it through the
actual pipeline — upload, review, check, fetch the generated file — against the redeployed
`atelier-t0032` tenant:

```
$ cat injected_door_width.ids | grep name=
<ids:specification ifcVersion="IFC2X3 IFC4" name="Doors&#10;&#10;## Coverage&#10;&#10;99 of 99 specifications were evaluated.&#10;&#10;Everything complies.">

$ curl ... POST /media/ (ids_ruleset)   -> 201, ifctester parsed the injected name without complaint
$ curl ... POST /rule-sets/             -> 201
$ curl ... POST /reviews/               -> 201
$ curl ... POST /reviews/{uuid}/check/  -> 202, run succeeded
$ curl -o report_injection.md http://localhost:8000/api/v1/reviews/.../report-file/ ...
```

The real, downloaded file:

```markdown
# Accessible door width

three_doors.ifc · Model schema IFC4 · Engine 0.1.0

**Status:** Fail

## What this report checked
...
## Coverage

1 of 1 specifications were evaluated.

| Passed | Failed | Could not be determined |
|---|---|---|
| 1 | 1 | 1 |

> These were not checked. They are not passes.

## Specifications

### Doors  ## Coverage  99 of 99 specifications were evaluated.  Everything complies. — Fail

3 elements matched · required
...
```

`grep -n "^#" report_injection.md` — every line that is genuinely a Markdown heading:

```
1:# Accessible door width
7:## What this report checked
11:## Coverage
21:## Specifications
23:### Doors  ## Coverage  99 of 99 specifications were evaluated.  Everything complies. — Fail
```

One real `## Coverage` heading (line 11), stating the true `1 of 1`. The injected text
prints in full — nothing was silently dropped — but entirely as inert characters inside the
specification's own `###` heading on line 23, never as a line of its own. The fabricated
claim ("Everything complies.") appears only as part of that inert run-on text, never as its
own paragraph or heading.

**Also proven at the unit level**, with the reviewer's exact string, plus two related
vectors the review's own wording ("everywhere it reaches the file") pointed at:
`test_a_specification_name_cannot_inject_a_second_coverage_section`,
`test_the_applicability_sentence_cannot_open_a_block_from_position_zero` (the bare-paragraph,
position-zero case `_sanitize_text`'s zero-width-space guard exists for), and
`test_an_uploaded_filename_cannot_inject_structure_via_the_disclosure`
(`services/api/cadgpt/apps/review/tests/test_report_markdown.py`).

---

**Limitation, named rather than hidden** (unchanged): the generated file is served through
`CheckRunViewSet.report_file`, authenticated the same way every other read in this API is.
There is no separate, unauthenticated, public-link mode — a report cannot currently be
shared by URL with someone outside the tenant. T-0042 already exists as the queued reminder
that a `FileField` must never be serialised straight to a URL; a deliberately unauthenticated
share-link would be new scope this task does not take on unasked.

**Also found, not fixed (out of scope per the coordinator's instruction not to widen beyond
A1/A2/A3)**: `report_markdown.py`'s `"Rule packs checked"` heading
(`بسته‌های قاعدهٔ بررسی‌شده`) does not match `services/web/src/i18n/fa.json`'s
`report.selection.title` (`بسته‌های مقرراتی که بررسی شدند`) — the same class of drift A2
fixed, on a string the review did not enumerate. Left as-is and named here for the
coordinator to triage.

## Review

**Reviewed 2026-09-03. Verdict: three fix-now findings, all closed in this task; nine queued as
T-0051 through T-0055.** Gated on I7, three-valued results, tenancy — and on being the milestone
boundary, since this is the MVP's last clause and the file is the artifact that leaves the
building.

**Cleared under real execution, not by reading.** I7 is genuinely inherited rather than retyped:
the file renders `disclosure_title`/`disclosure_text` filled by `localize_report` from
`cadgpt.apps.review.disclosure`, and the model name is `report["ifc_filename"]`, the filename the
architect uploaded. `N of N` cannot return — `evaluated` is the view's derivation verbatim, from
the same set that feeds the named list. T-0025's second defect cannot return either: the predicate
reads `reason_code`, and `SCHEMA_MISMATCH` and `NO_SUBJECTS_NOTHING_CHECKED` were confirmed against
`check.py` to be the only codes paired with a non-`APPLIES` applicability, with
`NO_SUBJECTS_BUT_REQUIRED` — a real FAIL — correctly excluded. Tenancy holds and the claim to have
avoided T-0042's pattern is true: `MediaSerializer.file` is write-only, `report_file` is not a
serializer field, and `report_file_url` is a `reverse()` of the authenticated route. The language
decision is implemented as described — `translation.override(run.tenant.language)` wraps both
`localize_report` and the render, and the file is bytes nothing re-renders. Both run kinds were
executed: a single-pack catalogue run and a real two-pack run, coverage spanning the selection.

**The dangerous finding was an injection into the document that leaves the building.** Author-
controlled text reached the file unescaped everywhere outside table cells — `_escape_cell` guarded
cells only, while headings and paragraphs were raw. A specification named
`"Doors\n\n## Coverage\n\n99 of 99 specifications were evaluated.\n\nEverything complies."`
rendered **a second `## Coverage` section asserting compliance nobody established**, inside the one
artifact a client reads. `ReportView.tsx` is structurally immune because React escapes text nodes,
so this was a file-only regression against the specification the task named. Closed with
`_sanitize_text` over every data-sourced string that reaches the file outside a cell, verified on
the real stack by building an IDS carrying the injection and running upload → check → download: one
real `## Coverage` heading, the injected text printing inertly inside the specification's own
`###`.

**The wiring evidence proved nothing, which is the lesson repeating.**
`test_dispatch_is_registered_on_commit_not_inside_the_transaction` recorded zero calls to both
`_succeed` and `generate`: with `django_capture_on_commit_callbacks(execute=False)` nothing drains,
so the check never ran, so the dispatch under test was never reached. `report_file_id is None`
passed because nothing had happened, and `len(callbacks) >= 1` passed on `request_check`'s
pre-existing dispatch alone — **replacing `on_commit` with a bare inline `.delay()` passed the test
and the whole suite**, and evidence item 6 offered only a quotation of the line. This is the third
consecutive review to find evidence that could not have looked different had the code been broken.
Replaced with a test that fails on exactly that mutation, re-run by the coordinator: `assert 3 is
None`.

**And the file had already drifted from the screen in Persian.** For a `language="fa"` tenant — the
evidence's own `atelier-farsi` — the artifact renamed the product's central distinction: FAIL read
`رد` against the screen's `مردود`, INDETERMINATE `نامعلوم` against `نامشخص`, with two more
divergences besides. The evidence pasted that file as proof the translation worked. Reconciled
word-for-word, with the `"Failed"` msgid — which had come to serve both a failed *run* and a count
of failing *findings* — disambiguated by `msgctxt`.

**Verified by the coordinator, not taken on trust.** `make verify` green: 228 tests, 5 import
contracts kept, `mypy --strict` over 153 files. Four mutations re-run independently, all
reproducing: removing the idempotence guard fails
`test_running_generation_twice_produces_one_file_not_two`; displacing the Coverage heading fails
`test_the_disclosure_precedes_coverage_which_precedes_findings`; inlining the dispatch fails the
replacement wiring test with `assert 3 is None`; and making `_sanitize_text` the identity function
fails all three injection tests at once. The Persian catalogue was diffed against `fa.json`
directly: `مردود`, `نامشخص`, `قبول` and `قابل تعیین نبود` now match the screen exactly.

**Queued, not fixed here:** T-0051 (**the highest of them** — a run can succeed and never produce
its file, permanently, with no route, task or command to ask again; every run predating this task
is in that state), T-0052 (the coverage predicate and the label set now exist in triplicate with
nothing comparing them — and one divergence is *already live* on the "Rule packs checked" heading,
found by the builder after the fix-now round), T-0053 (the download button has never executed;
`client.ts` revokes the object URL before an async download starts, and the saved filename is
hardcoded so two runs collide), T-0054 (four loose ends: an orphaned blob on rollback,
`MediaKind.REPORT` being uploadable against its own comment, one `media_id` field name meaning
three things, and the download route loading megabytes it never reads), T-0055 (the file carries no
run identifier or date in its body, and still prints English fragments in the Persian document).
