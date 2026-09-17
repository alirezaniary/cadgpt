# T-0061 — Four loose ends in the report-generation failure record

**Phase:** 3   **Status:** done
**Touches invariants:** none. Four low-severity findings, batched — they are one pass over two files.

## Why

All found by the T-0051 review. Each is small; together they are the difference between a failure
record that can be trusted and one that happens to be right today.

1. **Every `ValidationError` from `MediaService.store` is recorded as `TOO_LARGE`.**
   `report_generation.py:119-125`. `MediaService._validate` (`media/services.py:64-84`) raises
   `ValidationError` for four distinct causes — unknown kind, wrong extension, size over limit *or*
   `upload.size is None`, and size zero — and the `except` also spans `Media.objects.store`. The
   reviewer checked reachability and cleared it **for today**: `render_markdown_report` always emits
   `# {title}`, so the upload is never empty; the name is always `.md`; the kind is always `REPORT`.
   It is queued anyway because the mislabel is **permanent** — writing `report_generation_error`
   removes the run from `missing_report` and from the backfill for good, so a future cause would be
   recorded under the wrong name and then hidden.

2. **`report_generation_detail` is documented as untranslated but captured under the tenant's
   language.** `models.py:183` says "not translated, not sent to a client"; `report_generation.py:126`
   evaluates `str(exc.message)` — a `gettext_lazy` proxy — inside
   `with translation.override(run.tenant.language)`. It is untranslated only by accident: the string
   "This file is larger than the %(limit)d byte limit." has no `fa` entry today. Add one and a
   Persian tenant's operator-facing detail and log line silently become Persian.

3. **The failed-state wording is composed in the frontend and hardcodes the only current cause.**
   `report.generationFailed` in both catalogues reads "…it was too large to store." and renders for
   *any* non-empty `report_generation_error` (`ReviewsPage.tsx:351`), while the backend already
   carries the translated label on `ReportGenerationFailure.TOO_LARGE` and sends only the code. A
   second enum member would silently tell the user the wrong reason. `CLAUDE.md`: *the engine names
   reasons with codes and the service supplies the wording* — this inverts it.

4. **Orphaned report blobs.** `generate` calls `MediaService.store` inside `transaction.atomic()`,
   so bytes reach storage before the commit. A worker killed between the two rolls back the `Media`
   row and leaves the file; `acks_late` redelivery writes another. Nothing reaps them. Storage-only,
   never user-visible. *(This is the same defect as T-0054's first item, which came from T-0032's
   review over the same code — close them together.)*

Also trivial, no task of its own: the new `fa.po` comment names `CheckRunViewSet.generate_report_file`;
the method is `generate_report`.

## Scope

Each of the four closed. (1) the recorded reason names the actual cause, and an unrecognised cause is
visibly unresolved rather than confidently mislabelled — `reasons.label_for`'s degradation is the
pattern this repository already settled on. (2) the docstring and the code agree. (3) the wording
comes from the code the server already sends. (4) closed once, with T-0054.

**What explicitly does not change** — the `TOO_LARGE` decision, the recovery path, `missing_report`'s
semantics.

## How to prove it ran

`make verify`, then: a non-size `ValidationError` forced through `store` and shown recorded under a
name that is not `TOO_LARGE`; the detail field proven untranslated with a `fa` entry present for the
message; the failed-state sentence rendered from a second enum member and saying the right thing;
and a crash between store and commit leaving no orphan.

## Evidence

**Scope correction, confirmed before starting (per the dispatching coordinator's note):**
item 4 (orphaned report blobs) was already closed by T-0054 -- confirmed still true:
`uv run pytest services/api/cadgpt/apps/review/tests/test_report_generation.py -k orphan -v`
→ `test_a_crash_between_storing_and_attaching_leaves_nothing_orphaned ... PASSED` (1 passed).
Nothing in that code path (`_attach`, `_find_reusable_media`) was touched. Item 3's stale
`ReviewsPage.tsx:351` reference was re-pointed at `ReviewDetailPage.tsx`'s
`reportGenerationError` branch (T-0074 moved it); `report_generation_error` was confirmed
**not** exposed via any serializer before this task (only `failure_reason`/`failure_detail`
were, on `CheckRunSummarySerializer`) -- item 2 below adds it.

### What changed

1. **`services/api/cadgpt/apps/media/services.py`, `_validate`** -- each of the four
   `ValidationError` raises now carries a distinct `code` (`unsupported_kind`,
   `unsupported_extension`, `file_too_large`, `file_empty`), using `DomainError`'s own
   `code` kwarg (`base/exceptions.py`'s own contract: "`code` ... is the stable identifier
   a client switches on, and it must survive translation") -- no new taxonomy invented,
   just the mechanism the exception already had, actually used.
2. **`services/api/cadgpt/apps/review/choices.py`** -- added
   `ReportGenerationFailure.OTHER = "other", _("The rendered report could not be stored")`
   for every cause `_validate` can raise that is not the size cap.
3. **`services/api/cadgpt/apps/review/services/report_generation.py`** -- added
   `_FAILURE_BY_VALIDATION_CODE = {"file_too_large": ReportGenerationFailure.TOO_LARGE}`
   and `_record_failure` now does
   `locked.report_generation_error = _FAILURE_BY_VALIDATION_CODE.get(exc.code, ReportGenerationFailure.OTHER)`
   instead of hardcoding `TOO_LARGE` -- an unrecognised cause degrades to `OTHER`, visibly,
   the same rule `reasons.label_for` already applies to an unrecognised `ReasonCode`. The
   `TOO_LARGE` decision itself, the recovery path, and `missing_report`/`generation_failed`
   (both filter generically on blank/non-blank, never on which value) are untouched.
4. **Decision on item 2**: `report_generation_detail` is made the same shape as
   `CheckRun.failure_detail` -- translated, client-facing -- rather than pinning it
   operator-only. Justification: it was *already* being captured under
   `translation.override(run.tenant.language)` (report_generation.py's existing code, not
   a change), so "operator-only, not translated" was already false in practice, only
   silently so; and `failure_detail` is the repository's own established precedent for
   exactly this shape of field (`docs/decisions.md`, "Report prose belongs to the server,
   not to the frontend catalogue"). Changed: `models.py`'s docstring on
   `report_generation_detail` now states it is translated and client-facing (previously
   said the opposite); `CheckRunSummarySerializer.Meta.fields` gained
   `"report_generation_detail"` (`services/api/cadgpt/apps/review/api/v1/serializers.py:61`);
   migration `0009_alter_checkrun_report_generation_error.py` records the new `OTHER`
   choice (trimmed by hand to just this task's field -- `makemigrations --check --dry-run`
   also proposed an unrelated `AlterField` on `failure_reason`, reproduced identically on
   `main` before any of this task's edits, so left alone as pre-existing drift outside
   this task's scope).
5. **Frontend**: `report_generation_detail` added to `CheckRunSummary`
   (`services/web/src/api/types.ts`). `ReviewDetailPage.tsx`'s `reportGenerationError`
   branch now renders `reportGenerationDetail` (the server's own sentence, falling back to
   `t("report.generationFailedNoDetail")` only if blank, mirroring `failureDetail`'s own
   guard) instead of the hardcoded `t("report.generationFailed")` catalogue sentence, which
   is deleted from both `en.json` and `fa.json`. No lookup table from
   `report_generation_error` to wording was added -- the code is only used as a
   `data-report-generation-error` attribute, exactly how `failure_reason` is only used as
   `data-failure-reason`. T-0058's removal of the retry button on this branch is untouched.
6. **Trivial fix**: `django.po`'s comment on "A report can only be generated for a
   succeeded check run." now reads
   `cadgpt/apps/review/api/v1/views.py (CheckRunViewSet.generate_report, not succeeded)`
   (was `generate_report_file`, which is the Celery task's name, not this method's).
7. Two new Storybook stories (`ReportFileFailed`, updated; `ReportFileFailedOtherCause`,
   new) with `play` functions in `ReviewDetailPage.stories.tsx`, and two new mock handlers
   in `mocks/handlers.ts` (`reportFileFailed` updated to carry a real
   `report_generation_detail`; `reportFileFailedOther`, new) -- these are what item 3's
   real-path proof below runs.

### `make verify`

Full run, clean, after all changes:
```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 196 files already formatted
uv run mypy packages/engine/src services/api/cadgpt  -> Success: no issues found in 178 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres" -> 328 passed, 1 deselected, 39 warnings in 10.14s
pnpm run lint && typecheck && build && build-workbench && test-unit && test-storybook
  -> test-unit:      Test Files  2 passed (2) / Tests  6 passed (6)
  -> test-storybook: Test Files  9 passed (9) / Tests 37 passed (37)   (was 35 before this
     task's two new play functions; both new tests are in that count)
```
`make verify` exit code: `0`.

### Real path -- item 1 and item 2 (backend)

Forced through the exact `except ValidationError as exc: return self._record_failure(run,
exc)` line in `report_generation.py`, over a **real** succeeded check run (real IFC, real
IDS, real engine, real Celery task in eager mode) -- via a throwaway pytest file
(`test_t0061_scratch_real_path.py`, deleted after this evidence was captured; not part of
the shipped diff). `MediaService._validate` was monkeypatched to take its
`unsupported_kind` branch instead of the (currently unreachable) size branch, so the *real*
`generate()` code path hits the *real* mapping in `_record_failure`:

```
$ rtk proxy uv run pytest services/api/cadgpt/apps/review/tests/test_t0061_scratch_real_path.py -s -v
...
{"service": "ReportGenerationService", "run_id": "43aabeb2-...", "reason": "other",
 "detail": "این نوع پرونده پذیرفته نمی‌شود.", "event": "report_generation_failed", ...}
STATUS: succeeded
REPORT_FILE_ID: None
REPORT_GENERATION_ERROR: 'other'
REPORT_GENERATION_DETAIL: 'این نوع پرونده پذیرفته نمی‌شود.'
.
```
`run.report_generation_error == ReportGenerationFailure.OTHER` and
`!= ReportGenerationFailure.TOO_LARGE` -- a non-size cause is no longer mislabelled.

Second real run in the same file, real `TOO_LARGE` cause (cap turned down to 10 bytes, a
real render exceeding it), tenant language set to `fa`, no monkeypatch on `_validate`
itself -- proving item 2, that `report_generation_detail` is genuinely translated with a
real `fa` catalogue entry present today (not silently English):

```
{"service": "ReportGenerationService", "run_id": "1786441f-...", "reason": "too_large",
 "detail": "حجم این پرونده بیش از سقف 10 بایت است.", "event": "report_generation_failed", ...}
REPORT_GENERATION_ERROR: 'too_large'
REPORT_GENERATION_DETAIL (fa): 'حجم این پرونده بیش از سقف 10\xa0بایت است.'
.

============================== 2 passed in 3.22s ===============================
```
The Persian sentence is the real `msgstr` already present in
`cadgpt/locale/fa/LC_MESSAGES/django.po` for `"This file is larger than the %(limit)s
limit."` -- `django.mo` was rebuilt (`compile-messages`, part of `make verify`'s `test`
target) from the current `.po`, so this is what a Persian tenant's operator-facing detail
(and, since item 2's decision, the client-facing one) actually reads today, not a
theoretical future translation.

### Real path -- item 3 (frontend)

```
$ cd services/web && pnpm exec vitest run --project=storybook -t "Report File Failed" --reporter=verbose
 ✓ |storybook (chromium)| src/features/review/ReviewDetailPage.stories.tsx > Report File Failed 2756ms
 ✓ |storybook (chromium)| src/features/review/ReviewDetailPage.stories.tsx > Report File Failed Other Cause 698ms

 Test Files  1 passed | 8 skipped (9)
      Tests  2 passed | 35 skipped (37)
```
`ReportFileFailed`'s `play` function asserts the rendered `[data-testid="report-file-failed"]`
element's text is `"حجم این پرونده بیش از سقف 8.0 مگابایت است."` (the mock's
`report_generation_detail`, the real `TOO_LARGE` sentence's shape) and its
`data-report-generation-error` attribute is `"too_large"`. `ReportFileFailedOtherCause`
(new) sets `report_generation_error: "other"` and a completely different
`report_generation_detail: "پروندهٔ بارگذاری‌شده خالی است."`, and asserts the banner shows
*that* sentence and does **not** contain "سقف" (the size-cause word) -- proving the page
renders whatever the server sends rather than the one sentence it used to hardcode
(`t("report.generationFailed")`, deleted) for every non-blank `report_generation_error`.
Both stories run with zero code in `ReviewDetailPage.tsx` that knows the string `"other"`
exists -- confirmed by reading the diff: the only place `reportGenerationError` (the code)
is read is the `data-report-generation-error` attribute and the `!reportFileUrl &&
!reportGenerationError` truthiness check, never a lookup keyed on its value.

### Wiring (registration lines, quoted from the files they live in)

- `services/api/cadgpt/apps/media/services.py:75,84,96,100` -- each `_validate` cause now
  raises with its own `code=` kwarg, e.g. `raise ValidationError(..., code="file_too_large", ...)`.
- `services/api/cadgpt/apps/review/services/report_generation.py:98` --
  `_FAILURE_BY_VALIDATION_CODE: dict[str, ReportGenerationFailure] = {"file_too_large": ReportGenerationFailure.TOO_LARGE}`,
  consumed at `report_generation.py:223`:
  `locked.report_generation_error = _FAILURE_BY_VALIDATION_CODE.get(exc.code, ReportGenerationFailure.OTHER)`.
- `services/api/cadgpt/apps/review/choices.py:91` -- `OTHER = "other", _("The rendered report could not be stored")`.
- `services/api/cadgpt/apps/review/api/v1/serializers.py:61` -- `"report_generation_detail",`
  inside `CheckRunSummarySerializer.Meta.fields` (inherited by `CheckRunDetailSerializer`).
- `services/api/cadgpt/apps/review/migrations/0009_alter_checkrun_report_generation_error.py`
  -- `dependencies = [('review', '0008_alter_review_project_not_null')]`, the new migration
  head for the `review` app; `makemigrations review --check --dry-run` afterward reports
  only the pre-existing, unrelated `failure_reason` drift (identical to what it reported
  before any of this task's edits), confirming this migration captures exactly this task's
  model change and nothing else.
- `services/web/src/features/review/ReviewDetailPage.tsx:372-374` --
  `<p className="error" data-testid="report-file-failed" data-report-generation-error={reportGenerationError}>{reportGenerationDetail}</p>`.

### NOT DONE

Nothing. All four items in the task's "Why" section are closed (four, not three -- item 4
was already closed by T-0054 as the task file's own note says, confirmed still true above).
The trivial `.po` comment is fixed.

## Review

Not reviewer-gated — no invariant, diff fully read by the coordinator (318 lines across 13
files, mostly small edits plus a migration). `DomainError.code` was confirmed to genuinely
exist and survive as an attribute (`base/exceptions.py`); the new `_FAILURE_BY_VALIDATION_CODE`
mapping degrades an unrecognised cause to `OTHER` rather than mislabeling it `TOO_LARGE`,
matching `reasons.label_for`'s established degrade-visibly rule. `report_generation_detail`'s
docstring now matches what the code actually does (translated, client-facing) rather than the
reverse; the frontend renders it as given, with no lookup table keyed on
`report_generation_error`'s value, matching `failure_detail`'s already-established pattern.
The migration is scoped to exactly this task's field change — the builder correctly identified
and left alone a pre-existing, unrelated `failure_reason` drift that predates this task,
reproduced on `main` before any of its edits. Item 4 (the orphaned blob, already closed by
T-0054) was confirmed still passing and left untouched. Verified against real forced causes on
both new/changed backend paths (a genuine `unsupported_kind` recorded as `other`, not
`too_large`; a genuine `TOO_LARGE` run's detail rendering real Persian sourced from the
compiled catalogue) and two new Storybook `play` tests proving the frontend renders whatever
the server sends, not a hardcoded sentence.