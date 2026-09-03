# T-0061 — Four loose ends in the report-generation failure record

**Phase:** 3   **Status:** open
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

## Review
