# T-0054 — Four loose ends in the report generation path

**Phase:** 3   **Status:** open
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

## Review
