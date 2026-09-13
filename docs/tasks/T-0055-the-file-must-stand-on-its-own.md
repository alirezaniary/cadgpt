# T-0055 — The report file must stand on its own once it leaves the building

**Phase:** 3   **Status:** done
**Touches invariants:** I7 — say what was checked. **Reviewer-gated.**

## Why

Found by the T-0032 review. Both findings are about the same thing: the generated file is read
somewhere we do not control, by someone who has no access to the app, possibly months later.

1. **The file cannot be traced back to its run.** It carries no check date and no run identifier in
   its body — only in the filename, which the frontend currently discards (T-0053). Rename or
   archive the file and there is no way to establish which run produced it, against which model
   version, at what time. The product's entire claim is that a finding is traceable to its
   authority; a document that cannot be traced to its own run undercuts that at the last step.

2. **The Persian file still carries English fragments.** `cardinality` renders as `required` on the
   matched line, and `entity.detail` is `ifctester`'s English sentence. This is exact parity with
   the screen — the same fragments appear there — and T-0032 was explicitly forbidden from
   inventing presentation rules the view lacks, so the builder was right to leave them.

   But the stakes are different for the file. On screen, an English fragment in a Persian UI is a
   rough edge. In a document forwarded to a client or a plan reviewer, it is the sentence explaining
   *why* an element failed, unreadable to the person the report is for.

   `entity.detail` comes from upstream `ifctester` and is not ours to translate — **check whether
   upstream renders it translatably before writing anything** (`CLAUDE.md`: inherit before writing).
   `cardinality` is a payload value we already control, and T-0036 already queued the same defect on
   the screen — settle it in one place for both renderers, consistent with T-0052.

## Scope

**Changes**

- The file identifies itself: the run, the check date, and the engine version that judged it, in
  the body. `docs/decisions.md` already settled that engine version answers *"would this be judged
  the same way today"* — that is exactly the question a reader of an archived report has.
- The Persian file stops carrying English where the wording is ours to supply. Where it is not ours
  — upstream's detail sentence — the honest options are to inherit a translated form if upstream
  offers one, or to state plainly that the detail is upstream's words. Do not machine-translate a
  sentence whose precision is the point.

**What explicitly does not change**

- The presentation rules the view defines, except where this task deliberately settles a fragment
  for both renderers at once.
- The engine's own reason codes and labels, which already localize correctly.

## How to prove it ran

`make verify`, then a real generated file in both languages, pasted, showing the identifying block
and no English fragment whose wording we own. State explicitly what upstream `ifctester` does and
does not offer for `entity.detail`, with the check that established it.

## Evidence

**Changes**

- `services/api/cadgpt/apps/review/services/report_markdown.py`: `render_markdown_report`
  gained two required, keyword-only parameters, `run_uuid` and `checked_at`, and now emits
  an identifying line right after `**Status:**` — `gettext("Run %(run_id)s · Checked
  %(date)s")` — rendered in UTC so an archived file's reader in any timezone reads one
  unambiguous instant. `spec["cardinality"]` (the "N elements matched · <cardinality>"
  line) is now passed through the new `cardinality_label()` instead of printed raw. A
  one-time blockquote note was added under `## Specifications`: `gettext("Where shown,
  the Detail column is the checking engine's own wording, in English.")`.
- `services/api/cadgpt/apps/review/requirements.py`: added `cardinality_label(cardinality:
  str) -> str`, backed by `pgettext_lazy("specification cardinality", ...)` for
  `"required"`/`"optional"`/`"prohibited"` — the same three-value fix `ReportView.tsx`
  already applies on screen (T-0036, `report.cardinality.<token>`), reused here rather
  than reinvented, with `msgstr`s kept word-for-word identical to
  `services/web/src/i18n/fa.json`'s `report.cardinality.*`. Total: an unrecognised token
  degrades to itself, never a crash or a wrong translation.
- `services/api/cadgpt/apps/review/services/report_generation.py`: `generate()` now passes
  `run_uuid=run.uuid, checked_at=run.finished_at` into `render_markdown_report`, with an
  assertion that `finished_at` is set (it always is — see Wiring below).
- `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`: added the identifying-line
  msgid/msgstr, the three `msgctxt "specification cardinality"` entries, and the Detail
  caveat msgid/msgstr. Compiled with `make compile-messages`.
- Tests: `services/api/cadgpt/apps/review/tests/test_report_markdown.py` — every call site
  updated to supply `run_uuid`/`checked_at` (via a `_render` helper), plus four new tests:
  the identifying block's content, UTC normalization from a non-UTC input timezone, the
  translated (not raw) cardinality word, and the Detail-column caveat text.
  `services/api/cadgpt/apps/review/tests/test_report_generation.py` — the existing
  real-engine, real-HTTP integration test now additionally asserts the run id and check
  date appear in a file generated by a real end-to-end run.
- **Not changed**: `services/web/src/components/ReportView.tsx`,
  `services/web/src/i18n/*.json`, `presentation.py`'s output shape for the API/screen path.
  `ReportView.tsx` already translates `cardinality` correctly (T-0036); this task only
  gave the file renderer the equivalent fix, in its own Python module, without touching the
  view or its JSON contract.

**Upstream check for `entity.detail` (CLAUDE.md: inherit before writing)**

Checked directly against the installed `ifctester` 0.8.5 (`.venv/lib/python3.12/
site-packages/ifctester/`, the version pinned in this workspace):
- `grep -rn "gettext\|i18n\|locale" ifctester/*.py` — zero hits in the package's own code
  (the only matches anywhere under the install are inside the bundled Pyodide web-app's
  compiled JS assets, unrelated to this text).
- No `.po`/`.mo` files anywhere under the installed package (`find ... -iname "*.po" -o
  -iname "*.mo"` — empty).
- `facet.py`'s `Result.to_string()` and every subclass override (`AttributeResult`,
  `EntityResult`, `ClassificationResult`, ...) return hardcoded English f-strings, e.g.
  `f'The attribute value "{...}" does not match the requirement'` — no language parameter,
  no hook to override the wording. This is exactly the text that reaches
  `cadgpt_engine.check._outcome`'s `detail` field (`facet.failures`'s own `"reason"`,
  `check.py:193`), which `report.py`'s own docstring already calls "the raw text from
  ifctester" (`report.py:89`).

**Conclusion**: upstream offers no translated or translatable form of this sentence.
Machine-translating it would risk the sentence's precision (CLAUDE.md/task text); the
honest fix implemented is the one-time, plainly-stated note added to the file (see above),
not a silent untranslated fragment and not a guess at a Persian equivalent.

**`make verify`**

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 195 files already formatted
uv run mypy packages/engine/src services/api/cadgpt  -> Success: no issues found in 177 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
compile-messages + pytest -m "not postgres"  -> 318 passed, 1 deselected, 37 warnings
web-verify (lint, typecheck, build, build-workbench, test-unit, test-storybook)
  -> lint: 0 errors, 2 pre-existing warnings (react-refresh, unrelated files)
  -> typecheck/build: clean
  -> test-unit: 6 passed; test-storybook: 36 passed
```
Full `make verify` run: all five gates green, nothing skipped or silenced.

**Real path**

A real end-to-end run, through the real HTTP API and the real Celery task functions
(`CELERY_TASK_ALWAYS_EAGER` makes `.delay()` run the same task body a worker would, per
`cadgpt/config/settings/test.py`'s own docstring), against the real fixtures
`packages/engine/tests/fixtures/three_doors.ifc` + `door_width.ids` — one tenant with
`language="en"`, one with `language="fa"`, each: register → provision tenant → upload IFC
→ upload IDS → create rule set → create project → create review → `POST
/api/v1/reviews/<uuid>/check/` → `GET .../report-file/`. Script:
`/tmp/claude-1000/-home-alireza-Projects-cadgpt/7229a555-0596-4f1e-867b-050f276a0094/
scratchpad/real_path_check.py` (sqlite via `cadgpt.config.settings.test`, in-memory
storage — the same settings module the real test suite runs under).

Output (trimmed to the load-bearing lines):
```
===== en =====
POST /check status: 202
run status: succeeded outcome: FAIL
GET report-file status: 200
written: .../real-report-en.md bytes: 1340
run.uuid: 0a83ab86-3ab2-41c2-ae1d-b3d1cdf184f9
run.engine_version: 0.2.0
run.finished_at: 2026-09-13 20:50:38.504980+00:00

===== fa =====
POST /check status: 202
run status: succeeded outcome: FAIL
GET report-file status: 200
written: .../real-report-fa.md bytes: 1279
run.uuid: 6cf45164-6fc8-4a68-8e5a-6505dcc10f8c
run.engine_version: 0.2.0
run.finished_at: 2026-09-13 20:50:38.597567+00:00
```

Generated English file (`real-report-en.md`), in full:
```
# Accessible door width

three_doors.ifc · Model schema IFC4 · Engine 0.2.0

**Status:** Fail

Run 0a83ab86-3ab2-41c2-ae1d-b3d1cdf184f9 · Checked 2026-09-13 20:50 UTC

## What this report checked

This report checked the model three_doors.ifc — not the drawing set your office submits for review. A model and its submitted drawing set can diverge: detailing drawn directly onto a view, a schedule typed by hand, an area table in a titleblock. None of that divergence is checked here. The result below describes the model; it says nothing about the sheets.

## Coverage

1 of 1 specifications were evaluated.

| Passed | Failed | Could not be determined |
|---|---|---|
| 1 | 1 | 1 |

> These were not checked. They are not passes.

## Specifications

> Where shown, the Detail column is the checking engine's own wording, in English.

### Minimum clear door width 900 mm — Fail

3 elements matched · required

All IFCDOOR data

**The OverallWidth shall be at least 900.**

| Status | IFC class | Global ID | Reason | Detail |
|---|---|---|---|---|
| Fail | IfcDoor | 3worKcMPzD8x0Y1nJVBqA2 | The attribute value does not satisfy the rule. | The attribute value "800.0" does not match the requirement |
| Indeterminate | IfcDoor | 3worKcMPzD8x0Y1nJVBqA3 | The attribute is present but holds no value. | The attribute value "None" is empty |
```

Generated Persian file (`real-report-fa.md`), in full:
```
# Accessible door width

three_doors.ifc · شمای مدل IFC4 · موتور 0.2.0

**وضعیت:** مردود

اجرا 6cf45164-6fc8-4a68-8e5a-6505dcc10f8c · بررسی‌شده در 2026-09-13 20:50 UTC

## آنچه در این گزارش بررسی شد

این گزارش مدل three_doors.ifc را بررسی کرده است — نه مجموعه نقشه‌هایی که دفتر شما برای بازبینی ارائه می‌دهد. مدل و مجموعه نقشه‌های ارسالی می‌توانند با هم واگرا شوند: جزئیاتی که مستقیماً روی یک نما ترسیم شده، جدولی که دستی تایپ شده، جدول مساحت در کارتوش. هیچ‌یک از این واگرایی‌ها در اینجا بررسی نشده است. نتیجهٔ زیر مدل را توصیف می‌کند؛ دربارهٔ نقشه‌ها چیزی نمی‌گوید.

## پوشش

1 از 1 مشخصه بررسی شد.

| قبول | مردود | قابل تعیین نبود |
|---|---|---|
| 1 | 1 | 1 |

> این موارد بررسی نشدند و قبول به شمار نمی‌آیند.

## مشخصه‌ها

> در صورت نمایش، ستون «جزئیات» متن اصلی موتور بررسی به زبان انگلیسی است.

### Minimum clear door width 900 mm — مردود

3 عضو منطبق بودند · الزامی

همهٔ داده‌های IFCDOOR

**OverallWidth باید دست‌کم 900 باشد.**

| وضعیت | کلاس IFC | شناسهٔ سراسری | دلیل | جزئیات |
|---|---|---|---|---|
| مردود | IfcDoor | 3worKcMPzD8x0Y1nJVBqA2 | مقدار ویژگی قاعده را برآورده نمی‌کند. | The attribute value "800.0" does not match the requirement |
| نامشخص | IfcDoor | 3worKcMPzD8x0Y1nJVBqA3 | ویژگی موجود است ولی مقداری ندارد. | The attribute value "None" is empty |
```

**No English fragment whose wording we own remains in the Persian file.** The only
English left is: the specification name (`"Minimum clear door width 900 mm"`, IDS-author
data, not server prose — same as `ifc_filename`), IFC technical identifiers (`IfcDoor`,
`GlobalId` values, `OverallWidth`, `IFCDOOR` — schema names, not prose, unchanged by
T-0036/T-0052 either), and the two `Detail` column sentences — upstream `ifctester`
wording, now explicitly captioned as such (see the blockquote under `## Specifications`
in both files). `cardinality` (`"required"` → `"الزامی"`), the `Run`/`Checked` line, and
every other server-composed sentence are fully localized.

**Wiring**

- The task/message registration that actually produces this file:
  `services/api/cadgpt/apps/review/tasks.py:39`:
  `name="review.tasks.generate_report_file"` (the `@shared_task(...)` this is dispatched
  under), invoked from `services/api/cadgpt/apps/review/services/execution.py:356`:
  `transaction.on_commit(lambda: generate_report_file.delay(str(run.uuid)))` — fired only
  after a run's `SUCCEEDED` row actually commits, exactly the run whose id and finish time
  this task now embeds in the body.
- The identifying data's source, quoted from
  `services/api/cadgpt/apps/review/services/report_generation.py:140-145`:
  ```python
  assert run.finished_at is not None  # set with SUCCEEDED, in the same commit
  markdown = render_markdown_report(
      localized,
      run.rule_pack_selection,
      run_uuid=run.uuid,
      checked_at=run.finished_at,
  )
  ```
  `run.uuid` is `CheckRun`'s primary identifier (`UuidBaseModel`); `run.finished_at` is set
  in `execution.py`'s `_succeed`, in the same transaction that flips the row to
  `SUCCEEDED` and records `report.engine_version` (`execution.py:338-345`) — never a
  placeholder, never backfilled after the fact. The real-path run above shows both
  populated with real values (`run.finished_at: 2026-09-13 20:50:38.504980+00:00`,
  `run.engine_version: 0.2.0`), and the generated file's own body naming the same run id
  and the same minute.

**NOT DONE:** nothing. Both scope items (the identifying block; the Persian file's
English fragments where the wording is ours) are implemented, tested, and proven against
a real run in both languages. `presentation.py`/`ReportView.tsx` were deliberately left
untouched beyond nothing, per the task's own scope boundary — the cardinality fix lives
only in the Python file-renderer's own module, matching the screen's existing wording
rather than replacing its code.

### Fix-now round — F1 (evidence-block-false: the cardinality test didn't test the feature)

A review of the uncommitted diff found that
`test_cardinality_renders_as_a_translated_word_not_the_raw_token` asserted
`"3 elements matched · required"` under the autouse `english` fixture —
`pgettext("specification cardinality", "required")` returns `"required"` in English
whether or not `cardinality_label` is even called, so the test passed identically with the
function deleted (reviewer proved this by monkeypatching it to the identity function and
re-running: still green). The deeper gap: no test anywhere asserted the Persian output of
the file renderer at all — `grep -rn "الزامی|اختیاری|ممنوع|بررسی‌شده در|متن اصلی موتور"
--include=*.py services/api` returned nothing, so the `msgctxt "specification
cardinality"` `.po` entries (or the run-identifying line, or the Detail caption) could be
deleted or drifted and `make verify` would stay green while the Persian file silently
reverted to English.

**Fix**, in `services/api/cadgpt/apps/review/tests/test_report_markdown.py`:

- Imported `_is_persian` and `_persian` from `test_check_run.py` (T-0083's helpers,
  written for exactly this failure mode) rather than reinventing a weaker check, and added
  a local `_persian_pgettext(context, msgid)` — the `pgettext` analogue of `_persian`,
  needed because `cardinality_label` renders through `pgettext_lazy("specification
  cardinality", ...)`, not bare `gettext`; a plain `_persian` lookup would miss the
  `msgctxt` and could silently compare against an unscoped `msgid` of the same spelling.
- Left the original (weak) test in place as a structural check only, with a docstring now
  stating plainly that it cannot detect the feature, and added
  `test_cardinality_renders_as_the_persian_word_when_the_active_language_is_persian`,
  which renders under `translation.override("fa")` and asserts the real compiled Persian
  word (`_persian_pgettext("specification cardinality", "required")`, itself checked with
  `_is_persian`) appears in the output, and that the raw English token does not.
- Added `test_the_detail_column_caption_is_translated_when_the_active_language_is_persian`
  and `test_the_file_identifies_its_run_and_check_date_when_language_is_persian` — both
  render under `fa`, compute the expected string from the real compiled catalogue via
  `_persian`, confirm it via `_is_persian`, and assert it in the rendered file. These close
  the reviewer's item 3: neither the run-identifying line nor the Detail caption had any
  Persian-language assertion anywhere before this round.
- F2–F6 (the requirements.py/fa.json drift test, the dropped `_sanitize_text` call, the
  unenforced `finished_at` invariant, the Detail-caption misattribution, and the
  undocumented date-format decision) were left untouched — filed by the coordinator as
  `docs/tasks/T-0086` through `T-0090`, out of scope for this round.

**Mutation check** (the same one the reviewer used, re-run here to prove the new tests
actually detect the feature this time): `cardinality_label` in
`services/api/cadgpt/apps/review/requirements.py` was temporarily changed to `return
cardinality` (identity, no translation) and the relevant tests re-run.

Before mutation, all four cardinality/detail/identity Persian-and-English tests pass:

```
$ uv run pytest cadgpt/apps/review/tests/test_report_markdown.py \
    -k "cardinality or detail_column_caption or identifies_its_run" -v
collected 26 items / 22 deselected / 4 selected
cadgpt/apps/review/tests/test_report_markdown.py ....                    [100%]
======================= 4 passed, 22 deselected in 0.22s =======================
EXIT=0
```

After mutation (`cardinality_label` reverted to identity), the new Persian test fails
while the old English test still passes — proving the old test was blind to exactly this
regression and the new one is not:

```
$ uv run pytest cadgpt/apps/review/tests/test_report_markdown.py \
    -k "cardinality or detail_column_caption or identifies_its_run" -v
cadgpt/apps/review/tests/test_report_markdown.py .F..                    [100%]
FAILED test_cardinality_renders_as_the_persian_word_when_the_active_language_is_persian
E   AssertionError: assert '· الزامی' in '# Accessible door width\n\nthree_doors.ifc ·
    شمای مدل IFC4 · موتور 0.1.0\n\n**وضعیت:** مردود\n\nاجرا aaaaaaaa-bbbb-cc...'
================== 1 failed, 3 passed, 22 deselected in 0.29s ==================
EXIT=1
```

`cardinality_label` was then restored to its original body (`git diff --stat` against
`HEAD` for `requirements.py` shows only the original T-0055 addition, `33 insertions(+)`,
`0 deletions` — the temporary mutation left no trace). Full suite re-run clean:

```
$ uv run pytest cadgpt/apps/review/tests/test_report_markdown.py -v
collected 26 items
cadgpt/apps/review/tests/test_report_markdown.py ....................... [ 88%]
...                                                                      [100%]
============================== 26 passed in 0.21s ==============================
EXIT=0
```

**`make verify`, full run, after the fix:**

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 195 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
                                -> Success: no issues found in 177 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest -m "not postgres"
                                -> 321 passed, 1 deselected, 37 warnings in 5.71s
web-verify (lint, typecheck, build, build-workbench, test-unit, test-storybook)
  -> lint: 0 errors, 2 pre-existing warnings (unrelated files)
  -> typecheck/build: clean
  -> test-unit: 6 passed; test-storybook: 36 passed
EXIT_CODE=0
```

(321 vs. the earlier evidence's 318 — the three new fa-locale tests added this round; the
weak English cardinality test was kept, narrowed to a structural-only docstring, not
deleted, per the reviewer's framing that it tests something real, just not the feature.)

**NOT DONE (this round):** nothing in F1's scope. F2–F6 remain queued as separate task
files per the coordinator's instruction and are not addressed here.

## Review

**Verdict: correct, reviewer-gated on I7, one fix-now round, closed.** Reviewer independently
re-derived the real path (own script, both languages, real engine and Celery-eager task body)
and reproduced the evidence block's generated files byte-for-byte; re-ran `make verify` rather
than trusting the paste; confirmed the `cardinality_label` wording matches
`services/web/src/i18n/fa.json` byte-for-byte; confirmed live against the installed
`ifctester` 0.8.5 that it has no i18n support anywhere, so the "upstream offers nothing
translatable" claim is true rather than assumed; and confirmed `run.finished_at` has exactly
one writer, inside the same transaction as `SUCCEEDED`, so the new assert's premise holds
today.

**FIX NOW (1), closed same task:** F1 — the evidence block's claim of "the translated (not
raw) cardinality word" test was false; the test could not distinguish the feature from its
absence (proved by the reviewer via a monkeypatch-to-identity mutation that still passed),
and no test anywhere asserted the Persian output of any of this task's new rendering at all.
Fixed in the round above: three new fa-locale tests, reusing `_is_persian`/`_persian`
(T-0083's helpers) rather than a weaker bespoke check, mutation-verified by the same
identity-function reversion the reviewer used — the new test now fails exactly where the old
one didn't. `make verify` re-run clean, 321 passed.

**QUEUED, not fixed here — T-0086 through T-0090:** the cardinality wording's duplication
with `fa.json` has no drift test (**T-0086**, same shape as T-0052's precedent); the
`cardinality_label()` interpolation dropped the `_sanitize_text()` call the field used to go
through, not reachable via any input today but a real narrowing of a defensive property
(**T-0087**); the new `finished_at is not None` assert is backed by convention, not a
database constraint, and sits outside `generate()`'s own `try` so one bad row would abort a
whole backfill sweep (**T-0088**); the Detail-column caption says "the checking engine's own
wording" when the sentence is upstream `ifctester`'s, misattributing it to `cadgpt_engine`
(**T-0089**); and the file's Gregorian-UTC date format versus the screen's local-calendar
format is a real, reasoned, but undocumented divergence — CLAUDE.md's decision-log rule was
not followed (**T-0090**). None blocks this task's own claim; none is a fix-now finding.
