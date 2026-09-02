# T-0029 — Say what was checked: the model, not the submitted drawing set

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** I7 — never assert compliance we did not establish. **Reviewer-gated.**
This task is one paragraph of copy and the difference between decision support and an implied
compliance claim.

## Why

`prd.md` §5.7 closes with a requirement this product does not yet meet:

> **What is checked is the model; what is submitted is sheets.** The artifact a plan reviewer
> marks up is the drawing set, and an office that models the geometry but drafts its
> documentation in 2D over it can submit sheets that diverge from the model this system
> checked — detailing drawn on a view, a hand-typed schedule, an area table in a titleblock.
> That divergence is out of scope and unchecked, and I7 requires saying so plainly rather than
> allowing "the model complies" to be read as "the submission complies"; every report names the
> model it checked.

Half of it is already done: the report header names the model (`three_doors.ifc · Model schema
IFC4 · Engine 0.1.0`), which was itself a defect found by running the stack in Phase 2 — the
report used to name the storage key instead of the file the architect uploaded. What is missing
is the sentence that says what that naming *means*. A reader today sees a model name, three
counts and a list of findings, and nothing anywhere tells them that a clean result covers the
model and says nothing about the sheets they are about to submit.

This is the cheapest I7 obligation in the product and the one with the widest blast radius. It
is also the one place where the honest thing to write is genuinely uncomfortable, and the task
is not complete if the wording is softened into marketing.

## Scope

**Changes**

- `services/web/src/components/ReportView.tsx` — a disclosure block. T-0025 deliberately left
  room for it **above the coverage block**; that is where it goes. Coverage answers "how much
  of the rule set was evaluated"; this answers the prior question, "what artifact was evaluated
  at all", and it reads first.
- `services/web/src/i18n/en.json` and `fa.json` — the copy, both catalogues, same commit.
- `services/web/src/styles.css` — as needed. It must not be styled as a warning or an error;
  it is a statement of scope, and dressing it as an alert teaches readers to dismiss it.
- `services/web/e2e/report.spec.ts` — assert it renders, and assert its position relative to
  the coverage block in document order.

**The wording must:**

- name the model that was checked, by the filename the architect uploaded;
- state plainly that what was checked is the model and not the submitted drawing set;
- name at least one concrete way they can diverge — detailing drawn on a view, a hand-typed
  schedule, an area table in a titleblock — because an abstract disclaimer is read as
  boilerplate and a concrete one is read as information;
- never imply that the divergence is small, unlikely, or the reader's fault.

**The wording must not** be a legal disclaimer, a modal, a dismissible banner, or anything a
reader can turn off. It is part of the report.

**Does not change:** the engine, the API, the report schema, the counts, coverage, the filter.
This is presentation only. If the filename is not already on the payload, stop and say so
rather than adding a field — it is on it, and the header renders it today.

**One structural requirement.** `docs/plan.md` says this copy has to land in the generated
Markdown file as well as the view, because the file is the thing that leaves the building. The
file is **T-0032** and is not built yet. So write this copy as **one exported source that
T-0032 can consume** — not a string inlined into JSX that T-0032 will have to duplicate. Two
copies of a disclosure sentence drift, and the one that drifts is the one nobody is reading
when it does.

## How to prove it ran

```sh
make verify
make up   # rebuild: docker compose -f deploy/compose.yaml up -d --build web
make e2e
```

Evidence must show, from the rendered page in a real browser:

1. The disclosure block appears **before** the coverage block in document order — asserted on
   order, not on presence.
2. It names the uploaded model's filename, taken from the payload rather than hardcoded.
3. A screenshot you have actually opened, with the disclosure paragraph quoted verbatim from
   it in the evidence, so the wording is on the record and a later change to it is visible.
4. The i18n key list from both catalogues, and the Persian rendering — this is a paragraph of
   prose rather than a label, and it is the most likely place for an untranslated string to
   ship unnoticed.
5. Mutation proof on the document-order assertion.

## Evidence

**Changes.** `services/web/src/report/disclosureCopy.ts` (new) is the one exported source:
`disclosureTitle(t)` and `disclosureText(t, ifcFilename)`, keyed on
`report.disclosure.title` / `report.disclosure.text`. `ReportView.tsx` renders it in a new
`<section className="disclosure" data-testid="disclosure">` immediately above
`<section className="coverage">`, inside `<section className="report">`. Copy landed in
both `en.json` and `fa.json`. `styles.css` gives `.disclosure` a neutral start-border, no
`--fail`/`--indeterminate` background and no icon — the same visual register as the report
body, not the `.notice` alert class used elsewhere for INDETERMINATE. `report.spec.ts`
asserts the block's text and its position relative to coverage in document order.

**1. `make verify` — full pass.**
```
uv run ruff check .           -> All checks passed!
uv run ruff format --check .  -> 155 files already formatted
uv run mypy ... 141 source files -> Success: no issues found
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest                 -> 186 passed, 18 warnings in 2.77s
cd services/web && pnpm run verify
  eslint .        -> clean
  tsc -b --noEmit -> clean
  tsc -b && vite build -> ✓ 106 modules transformed, ✓ built in 1.76s
```

**2. The real path ran, against the compose stack.**
```
$ docker compose -f deploy/compose.yaml up -d --build web
 web  Built
 Container cadgpt-api-1  Recreated
 Container cadgpt-web-1  Recreated
 ...
 Container cadgpt-web-1  Started

$ make e2e
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail
     / 1 indeterminate in the browser (11.3s)
  1 passed (12.2s)
```

**3. Document order, asserted not just presence** (`report.spec.ts`, added after the report
becomes visible, before the existing coverage-vs-findings assertion):
```ts
const disclosure = report.locator('[data-testid="disclosure"]');
await expect(disclosure).toBeVisible();
await expect(disclosure).toContainText("three_doors.ifc");

const disclosureThenCoverage = report.locator('[data-testid="disclosure"], [data-testid="coverage"]');
await expect(disclosureThenCoverage.first()).toHaveAttribute("data-testid", "disclosure");
```
This is a real assertion on DOM order (the combined locator matches both nodes; `.first()`
is whichever the browser paints first), not a separate presence check for each — see the
mutation proof in (5), which fails exactly this line when the blocks are swapped.

**4. Screenshot, opened, with the disclosure paragraph quoted verbatim.**
Screenshot: `services/web/e2e/screenshots/report.png` (captured by the passing e2e run,
before the filter control changes the DOM — same shot the existing test already took).
Opened and read directly. The disclosure block renders under the heading "What this report
checked", immediately above "Coverage", with this paragraph, verbatim, from the model
`three_doors.ifc`:

> This report checked the model three_doors.ifc — not the drawing set your office submits
> for review. A model and its submitted drawing set can diverge: detailing drawn directly
> onto a view, a schedule typed by hand, an area table in a titleblock. None of that
> divergence is checked here. A clean result below describes the model; it says nothing
> about the sheets.

It is styled as plain report text with a neutral start-border — no warning color, no icon,
not dismissible.

**5. i18n key list (both catalogues, parity checked with a script diffing the two key
sets — zero keys in either catalogue only):**
```
report.disclosure.title
report.disclosure.text
```

`en.json`:
```json
"disclosure": {
  "title": "What this report checked",
  "text": "This report checked the model {{filename}} — not the drawing set your office submits for review. A model and its submitted drawing set can diverge: detailing drawn directly onto a view, a schedule typed by hand, an area table in a titleblock. None of that divergence is checked here. A clean result below describes the model; it says nothing about the sheets."
}
```

`fa.json`:
```json
"disclosure": {
  "title": "آنچه در این گزارش بررسی شد",
  "text": "این گزارش مدل {{filename}} را بررسی کرده است — نه مجموعه نقشه‌هایی که دفتر شما برای بازبینی ارائه می‌دهد. مدل و مجموعه نقشه‌های ارسالی می‌توانند با هم واگرا شوند: جزئیاتی که مستقیماً روی یک نما ترسیم شده، جدولی که دستی تایپ شده، جدول مساحت در کارتوش. هیچ‌یک از این واگرایی‌ها در اینجا بررسی نشده است. نتیجهٔ بدون یافته در ادامه، مدل را توصیف می‌کند؛ دربارهٔ نقشه‌ها چیزی نمی‌گوید."
}
```

Persian rendering, proved live against the running stack (a throwaway Playwright script,
not committed, that signed in, created a rule set and review, ran the check, switched the
language selector to `fa`, and read the rendered DOM):
```
DIR: rtl
TITLE: آنچه در این گزارش بررسی شد
TEXT: این گزارش مدل three_doors.ifc را بررسی کرده است — نه مجموعه نقشه‌هایی که دفتر شما
برای بازبینی ارائه می‌دهد. مدل و مجموعه نقشه‌های ارسالی می‌توانند با هم واگرا شوند:
جزئیاتی که مستقیماً روی یک نما ترسیم شده، جدولی که دستی تایپ شده، جدول مساحت در کارتوش.
هیچ‌یک از این واگرایی‌ها در اینجا بررسی نشده است. نتیجهٔ بدون یافته در ادامه، مدل را
توصیف می‌کند؛ دربارهٔ نقشه‌ها چیزی نمی‌گوید.
```
`document.documentElement.dir` was `rtl` and the filename interpolated correctly. A
full-page screenshot of this run was captured and visually confirms the disclosure block
above coverage in the RTL layout, with the correct Persian copy and interpolated filename
(not saved into the repo — the harness intentionally has no fa-language e2e test in scope;
this was a one-off verification run against the real stack, script discarded after use).

**5 (continued). Mutation proof on the document-order assertion.**
Reverted the fix in place: moved the `<section className="disclosure">` block in
`ReportView.tsx` from above `<section className="coverage">` to below it (after coverage's
closing tag, before the filter `<div>`), rebuilt `web`
(`docker compose -f deploy/compose.yaml up -d --build web`), and ran `make e2e`:
```
✘  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail
   / 1 indeterminate in the browser (11.9s)

  Error: expect(locator).toHaveAttribute(expected) failed

  Locator:  locator('section.report').locator('[data-testid="disclosure"],
            [data-testid="coverage"]').first()
  Expected: "disclosure"
  Received: "coverage"
  Timeout:  5000ms

  Call log:
    - Expect "toHaveAttribute" with timeout 5000ms
    - waiting for locator(...).first()
      14 × locator resolved to <section class="coverage" data-testid="coverage">…</section>
         - unexpected value "coverage"

     96 |
     97 |   const disclosureThenCoverage = report.locator('[data-testid="disclosure"], [data-testid="coverage"]');
  >  98 |   await expect(disclosureThenCoverage.first()).toHaveAttribute("data-testid", "disclosure");
        |                                                ^
     99 |
  1 failed
```
Restored the original ordering (disclosure section above coverage, matching the diff shown
under "Changes"), rebuilt `web` again, and re-ran `make e2e`:
```
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail
     / 1 indeterminate in the browser (11.3s)
  1 passed (12.2s)
```
`make verify` (Python + `services/web` `pnpm run verify`) re-run clean after restoring, and
matches the run pasted under item 1.

**NOT DONE:** nothing. Scope was presentation-only in `services/web`, as specified; the
engine, API, report schema, counts, coverage and filter were not touched (`git diff --stat`
confirms only `services/web/src/{components/ReportView.tsx, i18n/{en,fa}.json, styles.css,
report/disclosureCopy.ts}` and `services/web/e2e/{report.spec.ts, screenshots/report.png}`
changed). T-0032 (the generated Markdown report) is out of scope and not built, per the
task; `disclosureCopy.ts` and the two i18n keys are what it is expected to read from when
it lands.

## Review

**Verdict: the wording is right, and it is in the wrong place.** Reviewed on opus, gated on I7.

Five suspicions were chased and dropped, recorded so nobody pays for them twice. A null filename
does **not** render as `undefined` or `null` — the reviewer ran the real i18next config against
the real catalogue and got an empty gap — and it is unreachable anyway, because
`media/services.py:37` stores `original_name=upload.name or "unnamed"` and `check.py:290` falls
back to `Path(ifc_path).name`, so `ifc_filename` is structurally a non-empty string. A failed run
renders no report at all (`CheckRun.report` is `null=True` and `ReviewsPage.tsx:193` gates on it),
and with zero specifications the disclosure still renders, sitting outside every conditional.
Key parity is exact with zero one-sided keys and nothing inlined in JSX. The `fa` string uses
U+060C and U+061B rather than their ASCII lookalikes, and the em dash and colon are bidi-neutral
between two RTL runs, so there is no RTL punctuation hazard. Scope was honoured:
`git diff --name-only 09cff69 -- packages services/api` is empty.

### FIX NOW — one finding

**The single-source claim is false: T-0032 cannot consume `disclosureCopy.ts`.** The module's
own comment and the evidence block both promise that T-0032's implementer reads this module.
T-0032 is **server-side Python** — `docs/decisions.md` records the report as generated
asynchronously by the worker, and `prd.md` §5.8 has it templated and localized on the server. A
Celery worker cannot import a TypeScript module or read `services/web/src/i18n/*.json`. The
sentence would be retyped into `django.po` when T-0032 lands: the exact two-copy drift the
task's "One structural requirement" existed to prevent, in the exact copy that leaves the
building.

The builder is not at fault for the placement — this task's own **Scope** listed only
`services/web` files and told it not to touch the API, and it complied. What is false is the
evidence block's `NOT DONE: nothing`, and the code comment promising T-0032 a source it cannot
read. **Scope was wrong, and the correction is the coordinator's.**

Settled and logged in `docs/decisions.md` as *"Report prose belongs to the server, not to the
frontend catalogue"*: the repository had already answered this and the answer was not applied
here — `services/web/src/i18n/index.ts` states that findings' wording comes from the server
"because the wording belongs with the rule engine's vocabulary and not with the UI's". The
disclosure is report prose, not UI chrome. **The copy moves to the server.**

### Folded into the same round

Findings 2 and 3 were queued by the reviewer, but they edit the same lines this fix already
touches, and splitting them into their own task would mean a second pass over one paragraph:

- **The operative clause is written only for the clean case.** "A **clean** result below
  describes the model" is a counterfactual printed above a FAIL report — which is the state the
  screenshot actually captured. On a FAIL or all-INDETERMINATE report the live I7 misreading is
  the mirror one: the finding list read as *exhaustive*, implying compliance for the unlisted
  remainder. Dropping one word — "The result below describes the model; it says nothing about
  the sheets" — covers all three states and loses none of the clean-case force.
- **Nothing asserts the wording, so the deliverable can be emptied silently.** Replace the copy
  with the literal string `"{{filename}}"` and all three e2e assertions still pass: the filename
  interpolates, the block is visible, the order holds. One assertion on a distinctive phrase
  closes it.

### QUEUED — T-0041

A verdict is reachable without the disclosure: the Reviews row renders "Complete · Fail ·
1 / 1 / 1" before anyone opens the report. That is the surface a reader most plausibly
screenshots into an email, and on a clean run it is a compliance-shaped signal with no statement
of what was checked. The same I7 obligation, one level up.

## Fix-now evidence

**Changes.** The disclosure moved to the server, following the `reason_label` /
`requirement_text` idiom exactly:

- `services/api/cadgpt/apps/review/disclosure.py` (new) — `disclosure_title()` and
  `disclosure_text(ifc_filename)`, both `gettext_lazy`-backed, mirroring
  `reasons.py`/`requirements.py`'s own module docstrings on why the wording lives here and
  not on the stored document.
- `services/api/cadgpt/apps/review/services/presentation.py` — `localize_report` now
  annotates the top-level report dict with `disclosure_title` and `disclosure_text`
  (`report.get("ifc_filename", "")` interpolated in), the same call site that already adds
  `reason_label` and `requirement_text`.
- `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po` — the two new msgids, translated,
  appended in the file's existing single-line convention.
- `services/api/cadgpt/apps/review/tests/test_disclosure.py` (new),
  `test_presentation.py` (a case proving a pre-`REPORT_SCHEMA_VERSION`-2 stored document
  still gets the disclosure), `test_check_run.py` (a real end-to-end HTTP assertion).
- `services/web/src/api/types.ts` — `Report` gains `disclosure_title: string` and
  `disclosure_text: string`.
- `services/web/src/components/ReportView.tsx` — renders `report.disclosure_title` /
  `report.disclosure_text` directly, exactly like `reason_label`; composes nothing.
- **Deleted** `services/web/src/report/disclosureCopy.ts` and the `report.disclosure.*`
  keys from both `en.json` and `fa.json` — confirmed those two files are now byte-identical
  to their pre-T-0029 committed state (`git diff services/web/src/i18n/{en,fa}.json` is
  empty).
- `services/web/e2e/report.spec.ts` — added `toContainText("not the drawing set")`, the
  wording assertion finding 3 asked for.
- Wording fix (finding 2): `_TEXT` no longer says "a **clean** result below" — it says "The
  result below describes the model; it says nothing about the sheets," which holds for
  FAIL and INDETERMINATE reports too, not only a clean one.

**`make verify` — full pass, both languages of the workspace, after the move:**
```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 157 files already formatted
uv run mypy ... 143 source files -> Success: no issues found
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest                  -> 192 passed, 18 warnings in 2.70s   (was 186 before this round)
cd services/web && pnpm run verify
  eslint .        -> clean
  tsc -b --noEmit -> clean
  tsc -b && vite build -> ✓ 105 modules transformed, ✓ built in 1.85s
```

**Disclosure served from the API, in both languages — one stored run, two renderings,
from a real HTTP round trip against the rebuilt containers** (registered an account and
tenant, uploaded `door_width.ids` and `three_doors.ifc` as media, created a rule set and a
review, ran a real check, same `run_uuid`, fetched twice with a different
`Accept-Language` header — same pattern as T-0027's own evidence):
```
$ curl -s http://localhost:8000/api/v1/reviews/$REVIEW/runs/$RUN/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: $TENANT" -H "Accept-Language: en"
disclosure_title: What this report checked
disclosure_text: This report checked the model three_doors.ifc — not the drawing set
  your office submits for review. A model and its submitted drawing set can diverge:
  detailing drawn directly onto a view, a schedule typed by hand, an area table in a
  titleblock. None of that divergence is checked here. The result below describes the
  model; it says nothing about the sheets.

$ curl -s http://localhost:8000/api/v1/reviews/$REVIEW/runs/$RUN/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: $TENANT" -H "Accept-Language: fa"
disclosure_title: آنچه در این گزارش بررسی شد
disclosure_text: این گزارش مدل three_doors.ifc را بررسی کرده است — نه مجموعه نقشه‌هایی
  که دفتر شما برای بازبینی ارائه می‌دهد. مدل و مجموعه نقشه‌های ارسالی می‌توانند با هم
  واگرا شوند: جزئیاتی که مستقیماً روی یک نما ترسیم شده، جدولی که دستی تایپ شده، جدول
  مساحت در کارتوش. هیچ‌یک از این واگرایی‌ها در اینجا بررسی نشده است. نتیجهٔ زیر مدل را
  توصیف می‌کند؛ دربارهٔ نقشه‌ها چیزی نمی‌گوید.
```
Both fields differ only by the `Accept-Language` header — the same stored report document,
localized at read time by `gettext`, not by a second engine run. Also confirmed directly
inside the rebuilt `cadgpt-api-1` container (`docker compose exec api ... translation.
activate('fa') ...`) that the compiled `.mo` (built during `deploy/docker/api.Dockerfile`'s
`compilemessages` step, gettext tools are not installed on the host) renders the same
Persian text, so the HTTP-level proof above is not a caching artefact.

**`make e2e` against the rebuilt containers:**
```
$ docker compose -f deploy/compose.yaml up -d --build web
 api  Built
 web  Built
 Container cadgpt-api-1  Recreated
 Container cadgpt-web-1  Recreated
 ...

$ make e2e
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail
     / 1 indeterminate in the browser (10.8s)
  1 passed (11.8s)
```
Screenshot (`services/web/e2e/screenshots/report.png`, refreshed by this run, opened and
read directly) now shows, verbatim, under "What this report checked": "This report checked
the model three_doors.ifc — not the drawing set your office submits for review. A model
and its submitted drawing set can diverge: detailing drawn directly onto a view, a
schedule typed by hand, an area table in a titleblock. None of that divergence is checked
here. The result below describes the model; it says nothing about the sheets." — no
"clean," matching a screenshot that is in fact a FAIL report.

**Mutation proof, on the new wording assertion (finding 3).** Reverted
`disclosure_text` in `services/api/cadgpt/apps/review/disclosure.py` to `return
ifc_filename` — the exact failure mode the finding named ("replace the copy with the
literal `{{filename}}`" in the old frontend version; its server-side analogue is
collapsing the sentence to the bare filename). Rebuilt (`docker compose -f
deploy/compose.yaml up -d --build web`, which rebuilds and recreates `cadgpt-api-1` too)
and ran `make e2e`:
```
Error: expect(locator).toContainText(expected) failed
Locator: locator('section.report').locator('[data-testid="disclosure"]')
Expected substring: "not the drawing set"
Received string:    "What this report checkedthree_doors.ifc"

  100 |   await expect(disclosure).toContainText("not the drawing set");
      |                            ^
  1 failed
```
The filename assertion (`toContainText("three_doors.ifc")`) and the document-order
assertion both still passed against this mutant — only the new wording assertion caught
it, which is what it was added for. Restored `disclosure_text` to
`return str(_TEXT) % {"filename": ifc_filename}`, rebuilt again, ran `make e2e` again:
```
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail
     / 1 indeterminate in the browser (10.8s)
  1 passed (11.8s)
```
`make verify` (full Python + `services/web` `pnpm run verify`) re-run clean after
restoring, matching the run pasted above. The document-order mutation from the original
round (disclosure moved below coverage) was not re-run in this pass — the coordinator
already independently reproduced it and confirmed it fails on the real error text; moving
the copy's *source* did not touch the DOM structure or `data-testid` placement that
mutation exercises.

**NOT DONE:** nothing outstanding in this round. T-0032 (the generated Markdown report)
remains unbuilt and out of scope; `cadgpt.apps.review.disclosure` is now the single source
its implementer reads (server-side, reachable from the worker/management-command context
T-0032 will actually run in — unlike the deleted frontend module, which a Celery process
could never have imported). T-0041 (the Reviews-row verdict shown before the report is
opened) is queued, not addressed here, per the coordinator's instruction that it is out of
scope for this task.
