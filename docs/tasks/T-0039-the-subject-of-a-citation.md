# T-0039 — The subject of a citation: structured in the engine, worded in the service

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** I5, and `CLAUDE.md`'s gettext rule. **Reviewer-gated.**

## Why

Two findings from the T-0027 review, and they are the same defect wearing two hats: T-0027
made the *predicate* of a citation structured and localizable and left the *subject* as English
prose written into the stored document by the engine.

**The attribute name can itself be a restriction, and then the dict repr comes back.**
`_facet_subject_name` in `packages/engine/src/cadgpt_engine/check.py` accepts `name`/`baseName`
only when `isinstance(..., str)`. But `Facet.parse` (`ifctester/facet.py:104-113`) is generic:
**any** parameter becomes a `Restriction` when the IDS writes `<xs:restriction>` under it,
including `name`. Reproduced on the real path:

```
SPEC: Restricted attribute name
    stored basis:     {"facet_type":"attribute","name":null,"cardinality":"required","comparisons":[]}
    requirement_text: "The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided"
```

`basis.name` is `null`, the sentence falls back to `description`, and the reader gets the Python
dict repr T-0027 exists to eliminate — as the primary, untranslatable line. The `isinstance`
guard is the right *defensive* shape, since it degrades rather than raising; what is wrong is
that it drops the data instead of carrying it.

**And the applicability line is untranslated English in the stored document.**
`_specification` builds `" and ".join(f.to_string("applicability") for f in spec.applicability)`
and `ReportView.tsx:175-179` renders it straight to the DOM. That is verbatim the defect
T-0027's own "Why" section opens with, reintroduced on a new field. The joiner `" and "` is
separately hardcoded English *inside the engine*, so a two-facet applicability reads
English-joined even in Persian. T-0027's builder disclosed this and justified it by that task's
no-renderer-registry ban, which was a defensible scope call — this is the task that closes it.

## Scope

The shape is the one `reason_code`/`reason_label` and now `basis`/`requirement_text` already
established. Do not invent a third mechanism.

**Changes**

- `packages/engine/src/cadgpt_engine/report.py`, `check.py` — carry the attribute name's own
  restriction rather than dropping it to `None` (a `name_comparisons`, or whatever fits the
  existing `Comparison` shape), and give `SpecificationOutcome` a **structured** applicability
  beside or in place of `applicability_description`. Wire-format change: bump
  `REPORT_SCHEMA_VERSION`, and keep the existing string field as the fallback for documents
  already stored at the current version.
- `services/api/cadgpt/apps/review/` — the wording, through `gettext`, beside the existing
  requirement wording. **Start with `Entity`**, the only applicability facet the shipped
  fixtures exercise; every other facet type falls back to the string the engine already
  produces. Do not build a registry for facet types no fixture exercises.
- `services/web/` — render the localized subject, falling back as today.
- Both i18n catalogues, and `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`.

**Does not change:** the predicate rendering T-0027 built, the fallback contract, any status or
count. Do not implement margin.

## How to prove it ran

A committed fixture whose IDS puts an `<xs:restriction>` under the attribute *name*, and one
with a two-facet applicability. Then, as T-0027 proved its own claim: **the same stored document
rendered in both languages**, pasted from the API response — one document, two renderings, for
the subject line as well as the predicate. A single-language paste does not prove this task.

`make verify`; `make up` with the containers rebuilt; `make e2e` asserting the localized subject
from the browser; a screenshot you have opened; and a mutation proof per new assertion.

## Evidence

### 0. What changed, file by file

**Structured data (engine)** — `packages/engine/src/cadgpt_engine/report.py`:
`REPORT_SCHEMA_VERSION` 3 → 4. `RequirementBasis` gains `name_comparisons: tuple[Comparison,
...] = ()` — the attribute/property *name*'s own restriction, the sibling of `comparisons`
for the value. New `ApplicabilityFacet` dataclass (`facet_type`, `name`, `predefined_type`,
`description`). `SpecificationOutcome` gains `applicability_facets: tuple[ApplicabilityFacet,
...] = ()`; `applicability_description` is untouched, still the whole-document fallback.

`packages/engine/src/cadgpt_engine/check.py`: new `_facet_subject_name_comparisons` (reuses
`_comparisons` on the `name`/`baseName` `Restriction` itself, mirroring `_facet_subject_name`'s
own `baseName`-then-`name` priority) wired into `_requirement_basis`. New
`_applicability_facet` (captures `name`/`predefinedType` only when they are a literal `str`;
`description` is that one facet's own `to_string("applicability")`, computed once) wired into
`_specification`, which now builds `applicability_description` from the same facets'
`.description` rather than calling `to_string` a second time.

**Wording (service)** — `services/api/cadgpt/apps/review/requirements.py`: new `_subject_name`
reads `name_comparisons`, rendering only `literal`/`enumeration` operators (joined with the
existing `_ENUMERATION_JOINER`, " or "/" یا "), falling back to `description` for anything else
(`pattern`, `minLength`, ...). `requirement_text` now tries `basis["name"]` first, then
`_subject_name(basis["name_comparisons"])`.

New `services/api/cadgpt/apps/review/applicability.py` (mirrors `requirements.py`/`reasons.py`):
`applicability_text(facets, fallback)`. Only `facet_type == "entity"` with a literal `name`
renders (`"All %(name)s data"` / `"All %(name)s data of type %(predefined_type)s"`); every
other facet type and shape falls back to that facet's own `description`. A new `_JOINER`
(`" and "`, reusing the existing msgid) joins the rendered facets — the fix for the engine's
hardcoded joiner.

`services/api/cadgpt/apps/review/services/presentation.py`: `localize_report` now also puts
`applicability_text` on every specification. `services/api/cadgpt/apps/review/services/
report_markdown.py`: switched from reading `applicability_description` to
`applicability_text` (the Markdown report is a second renderer of the same localized
document, per `docs/decisions.md`).

**Frontend** — `services/web/src/api/types.ts`: `RequirementBasis.name_comparisons?`,
`SpecificationOutcome.applicability_text: string` (required, alongside the now-fallback-only
`applicability_description?`). `services/web/src/components/ReportView.tsx`: renders
`spec.applicability_text` instead of `spec.applicability_description`.
`services/web/src/mocks/fixtures.ts`: every spec now carries `applicability_text` alongside
`applicability_description`.

**Catalogues** — `services/api/cadgpt/locale/fa/LC_MESSAGES/django.po`: two new msgids
(`"All %(name)s data"`, `"All %(name)s data of type %(predefined_type)s"`); the joiner reuses
the existing `" and "` entry `requirements.py` already added — one catalogue entry, not two.
`services/web/src/i18n/*.json` needed **no new entries**: `applicability_text` is report
prose composed server-side (`docs/decisions.md`, "Report prose belongs to the server, not to
the frontend catalogue"), the same reason `requirement_text` added none in T-0027; the
frontend only renders the string it is given. Noted here rather than silently skipped, since
the task's Scope names both web catalogues.

**Fixtures** — `packages/engine/tests/fixtures/door_name_restricted.ids` (title "Restricted
attribute name"): the requirement's own `<ids:name>` is `<xs:restriction>` with two
`<xs:enumeration>` members, reproducing the task's own repro exactly.
`packages/engine/tests/fixtures/door_width_named_applicability.ids` (title "Minimum door
width, for named doors"): a two-facet applicability (`Entity` + `Attribute`), the same
requirement as `door_width.ids`. Both added to `seed_rule_packs.py`'s `SEED_MANIFEST` so the
catalogue and `make e2e` can select them.

### 1. The real path: `--json`, both fixtures

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc \
    packages/engine/tests/fixtures/door_name_restricted.ids --json
{
  "schema_version": 4,
  ...
  "specifications": [
    {
      "name": "A recorded overall dimension",
      "applicability_description": "All IFCDOOR data",
      "applicability_facets": [
        {"facet_type": "entity", "name": "IFCDOOR", "predefined_type": null,
         "description": "All IFCDOOR data"}
      ],
      "matched": 3, "status": "INDETERMINATE", "passed": 2, "failed": 0, "indeterminate": 1,
      "requirements": [
        {
          "description": "The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided",
          "basis": {
            "facet_type": "attribute", "name": null, "cardinality": "required",
            "comparisons": [],
            "name_comparisons": [
              {"operator": "enumeration", "value": "OverallWidth"},
              {"operator": "enumeration", "value": "OverallHeight"}
            ]
          },
          "status": "INDETERMINATE", "passed": 2, "failed": 0, "indeterminate": 1,
          "entities": [
            {"global_id": "3worKcMPzD8x0Y1nJVBqA3", "ifc_class": "IfcDoor",
             "status": "INDETERMINATE", "reason_code": "ATTRIBUTE_EMPTY",
             "detail": "The attribute value \"[None, None]\" is empty"}
          ]
        }
      ]
    }
  ]
}
```

`basis.name` is `null` exactly as the task's own repro shows, and `name_comparisons` now
carries what used to be dropped — the enumeration, as an operator and two values, not a
Python dict repr.

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc \
    packages/engine/tests/fixtures/door_width_named_applicability.ids --json
{
  "schema_version": 4,
  ...
  "specifications": [
    {
      "name": "Minimum clear door width 900 mm, named doors only",
      "applicability_description": "All IFCDOOR data and Data where the Name is provided",
      "applicability_facets": [
        {"facet_type": "entity", "name": "IFCDOOR", "predefined_type": null,
         "description": "All IFCDOOR data"},
        {"facet_type": "attribute", "name": "Name", "predefined_type": null,
         "description": "Data where the Name is provided"}
      ],
      "matched": 3, "status": "FAIL", "passed": 1, "failed": 1, "indeterminate": 1
    }
  ]
}
```

Two applicability facets, each named as data; `applicability_description` is unchanged
(built from the same facets' `.description`, joined with the engine's own `" and "`, kept
only as the fallback).

### 2. The same stored document, two renderings — API response, both findings

Registered a real account and tenant, uploaded `three_doors.ifc`, seeded the catalogue
(`manage.py seed_rule_packs`, picking up both new fixtures), created two reviews and ran
real checks through the full HTTP stack (`docker compose`, containers rebuilt — see §4).

**Finding 1 — the restricted attribute name** (`run` against `door_name_restricted.ids`,
same `run_uuid` fetched twice, `Accept-Language` the only thing that differs):

```
=== EN ===
basis: {"name": null, "facet_type": "attribute", "cardinality": "required",
        "comparisons": [], "name_comparisons": [
          {"value": "OverallWidth", "operator": "enumeration"},
          {"value": "OverallHeight", "operator": "enumeration"}]}
description: The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided
requirement_text: The OverallWidth or OverallHeight shall be provided.

=== FA ===
basis: {"name": null, "facet_type": "attribute", "cardinality": "required",
        "comparisons": [], "name_comparisons": [
          {"value": "OverallWidth", "operator": "enumeration"},
          {"value": "OverallHeight", "operator": "enumeration"}]}
description: The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided
requirement_text: OverallWidth یا OverallHeight باید ثبت شده باشد.
```

`basis` and `description` are byte-identical in both responses — the stored document did
not change; `requirement_text` is the only field that differs, and only because of the
`Accept-Language` header.

**Finding 2 — the two-facet applicability** (`run` against
`door_width_named_applicability.ids`, same `run_uuid`, same two headers):

```
=== EN ===
applicability_facets: [{"name": "IFCDOOR", "facet_type": "entity",
                         "description": "All IFCDOOR data", "predefined_type": null},
                        {"name": "Name", "facet_type": "attribute",
                         "description": "Data where the Name is provided",
                         "predefined_type": null}]
applicability_description: All IFCDOOR data and Data where the Name is provided
applicability_text: All IFCDOOR data and Data where the Name is provided

=== FA ===
applicability_facets: [{"name": "IFCDOOR", "facet_type": "entity",
                         "description": "All IFCDOOR data", "predefined_type": null},
                        {"name": "Name", "facet_type": "attribute",
                         "description": "Data where the Name is provided",
                         "predefined_type": null}]
applicability_description: All IFCDOOR data and Data where the Name is provided
applicability_text: همهٔ داده‌های IFCDOOR و Data where the Name is provided
```

`applicability_facets` and `applicability_description` are byte-identical in both
responses. `applicability_text` is the only field that differs: in Persian the `Entity`
term localizes (`همهٔ داده‌های IFCDOOR`) and the `Attribute` term correctly stays English
(out of scope, falls back to `description`), joined by the localized joiner (`و`) rather
than the engine's own hardcoded `" and "` — one document, two renderings, and the two
facets inside it independently prove the fallback and the localization both work on the
same line.

### 3. `make verify`

```
$ make verify
uv run ruff check .                        All checks passed!
uv run ruff format --check .                189 files already formatted
uv run mypy packages/engine/src services/api/cadgpt   Success: no issues found in 172 source files
uv run lint-imports --no-cache              Contracts: 5 kept, 0 broken.
uv run pytest                               281 passed, 34 warnings in 4.50s
cd services/web && pnpm run verify          lint (1 pre-existing warning, unrelated) /
                                             typecheck / build / storybook build /
                                             test-unit (2 passed) / test-storybook (35 passed)
                                             all clean
```

Full log captured at the time of this run; exit code `0`.

### 4. `make up`, containers actually rebuilt

The sandbox's Docker daemon can pull base images but a build container's own `RUN` steps
have no outbound network on the default bridge network (`uv sync`'s fetch of the `hatchling`
PEP 517 backend for the local editable install failed with `Connection refused`, both with
and without the host's `HTTP_PROXY`/`HTTPS_PROXY`, and with explicit `--build-arg` proxy
vars — the daemon's own registry pulls use a different path than a build step's `RUN`).
`docker build --network host` (undocumented in `Makefile`, but no `Dockerfile` line changed)
gives the build step the host's own network namespace and both images build cleanly:

```
$ docker build --network host -f deploy/docker/api.Dockerfile -t cadgpt-api:latest .
...
Step 14/22 : RUN uv sync --frozen --no-dev
 + cadgpt-api==0.1.0 (from file:///app/services/api)
 + cadgpt-engine==0.2.0 (from file:///app/packages/engine)
...
Successfully tagged cadgpt-api:latest

$ docker build --network host -f deploy/docker/web.Dockerfile -t cadgpt-web:latest .
...
Successfully tagged cadgpt-web:latest
```

`docker compose -f deploy/compose.yaml up -d` (after `down`, so nothing carried over) then
brought up all six containers on the freshly-built images:

```
NAME                STATUS
cadgpt-api-1        Up (healthy)
cadgpt-beat-1       Up
cadgpt-postgres-1   Up (healthy)
cadgpt-redis-1      Up (healthy)
cadgpt-web-1        Up
cadgpt-worker-1     Up (healthy)
```

`manage.py seed_rule_packs` created the two new packs ("Restricted attribute name",
"Minimum door width, for named doors") alongside the five already seeded from earlier tasks.

### 5. `make e2e`

```
$ pnpm run e2e
Running 11 tests using 4 workers
  ✓  breadcrumbs.spec.ts
  ✓  onboarding.spec.ts
  ✓  report.spec.ts:34   (T-0026/T-0027/T-0037's own scenario, still green)
  ✓  report-recovery.spec.ts
  ✓  session-isolation.spec.ts (x2)
  ✓  upload-limit.spec.ts
  ✓  report.spec.ts:202  (T-0037 round 1, still green)
  ✓  report.spec.ts:292  (T-0037 round 2, still green)
  ✓  report.spec.ts:380  a restricted attribute name renders as its own sentence, never
                          the dict repr, and a two-facet applicability joins in the
                          reader's language
  ✓  report.spec.ts:511  the applicability subject localizes with the browser's own
                          language, not just the UI chrome (locale: "fa-IR")
  11 passed (44.5s)
```

`report.spec.ts:380` (English, this harness's tenant/browser default) asserts, from the
real browser:

```ts
await expect(requirementText).toHaveText("The OverallWidth or OverallHeight shall be provided.");
await expect(requirementText).not.toContainText("enumeration");
await expect(requirementText).not.toContainText("{'");
...
await expect(applicability).toHaveText("All IFCDOOR data and Data where the Name is provided");
```

`report.spec.ts:511` is the test that actually distinguishes `applicability_text` from
`applicability_description` in the DOM: `services/web` never sends `Accept-Language`
itself, and a real browser's own header is what `LocaleMiddleware` resolves against, so
`test.use({ locale: "fa-IR" })` is what makes the real browser ask for Persian. It asserts:

```ts
await expect(applicability).toHaveText("همهٔ داده‌های IFCDOOR و Data where the Name is provided");
await expect(applicability).not.toHaveText("All IFCDOOR data and Data where the Name is provided");
```

Screenshots opened and described:
- `services/web/e2e/screenshots/restricted-attribute-name.png` — the "Restricted attribute
  name" report, INDETERMINATE overall, showing "All IFCDOOR data" as the (single-facet,
  English) subject line and "The OverallWidth or OverallHeight shall be provided." as the
  requirement line, with one INDETERMINATE entity row (`[None, None]` empty) beneath it.
- `services/web/e2e/screenshots/two-facet-applicability.png` — the "Minimum door width, for
  named doors" report (English), FAIL overall, showing "All IFCDOOR data and Data where the
  Name is provided" as the subject line, "The OverallWidth shall be at least 900." as the
  requirement line, and the same 1 pass / 1 fail / 1 indeterminate entity split as
  `door_width.ids`.
- `services/web/e2e/screenshots/two-facet-applicability-fa.png` — the same report fetched
  by a `fa-IR` browser: the I7 disclosure, the coverage band, and the requirement line are
  all in Persian (pre-existing localization), and the subject line reads "همهٔ داده‌های
  IFCDOOR و Data where the Name is provided" — the `Entity` term translated, the
  `Attribute` term correctly left in English (out of this task's scope), joined by the
  localized "و".

### 6. Wiring

Structured data, engine (`packages/engine/src/cadgpt_engine/check.py`):

```python
# _requirement_basis
name_comparisons=_facet_subject_name_comparisons(facet),

# _specification
applicability_facets = tuple(_applicability_facet(f) for f in spec.applicability)
...
applicability_description=" and ".join(f.description for f in applicability_facets),
applicability_facets=applicability_facets,
```

Wording, service (`services/api/cadgpt/apps/review/requirements.py:157`):

```python
name = basis.get("name") or _subject_name(basis.get("name_comparisons") or [])
```

`services/api/cadgpt/apps/review/applicability.py:66`:

```python
def applicability_text(facets: list[dict[str, Any]] | None, fallback: str) -> str:
```

The line in `presentation.py` that puts it on the response
(`services/api/cadgpt/apps/review/services/presentation.py:76-79`, called from
`services/api/cadgpt/apps/review/api/v1/serializers.py`'s `CheckRunDetailSerializer.
get_report`, unchanged since T-0027):

```python
"applicability_text": applicability_text(
    spec.get("applicability_facets"),
    spec.get("applicability_description", ""),
),
```

The render site, `services/web/src/components/ReportView.tsx:292-296`:

```tsx
{spec.applicability_text && (
  <p className="muted" data-testid="applicability">
    {spec.applicability_text}
  </p>
)}
```

The seed manifest, `services/api/cadgpt/apps/rulepack/management/commands/
seed_rule_packs.py`'s `SEED_MANIFEST`, now includes `"door_name_restricted.ids"` and
`"door_width_named_applicability.ids"` — confirmed created (not skipped) in §4's seed run.

### 7. Mutation proofs

Each new load-bearing assertion, reverted and restored, `diff` confirmed byte-identical
after restore:

| Fix | Mutation | Test(s) that caught it |
| --- | --- | --- |
| `_facet_subject_name_comparisons` (check.py) | body replaced with `return ()` | `test_a_restricted_attribute_name_is_carried_as_name_comparisons_not_dropped`, `test_a_restricted_property_base_name_is_carried_the_same_way` fail: `assert () == (Comparison(...` |
| `_applicability_facet` (check.py) | `name`/`predefined_type` hardcoded to `None` | `test_an_entity_facet_becomes_structured_data_with_its_class_name`, `test_an_entity_facet_with_a_predefined_type_carries_it_too`, `test_a_non_entity_facet_still_carries_its_own_name_as_data` fail: `assert None == 'IFCDOOR'` etc. |
| `_subject_name` (requirements.py) | body replaced with `return None` | `test_a_restricted_attribute_name_becomes_a_disjunctive_subject_not_a_dict_repr`, `test_a_single_member_restricted_name_reads_as_a_plain_subject` fail: renders the raw dict-repr fallback / `'fallback'` instead of the sentence |
| `_facet_text` (applicability.py) | body replaced with `return facet.get("description")` | 4 tests fail (single entity, predefined-type entity, two-entity join, mixed join) — all render the (deliberately distinguishable) `description` placeholder instead of the template |
| `applicability_text`'s `facets is None` fallback | replaced with `facets or []` | `test_a_document_stored_before_applicability_facets_existed_falls_back_whole` fails: `assert '' == 'All IFCDOOR ...'` |
| `presentation.py` wiring | `applicability_text` key removed from the dict | `test_a_v1_schema_document_still_gets_an_applicability_text_through_the_fallback`, `test_a_v2_schema_document_with_no_applicability_facets_falls_back_to_the_string` fail: `KeyError: 'applicability_text'` |
| `ReportView.tsx` render field | `spec.applicability_text` swapped back to `spec.applicability_description` | English e2e assertions do **not** catch this (upstream's English happens to equal the gettext template's English, by design — see the module docstring); `report.spec.ts:511`'s `fa-IR` assertion does: `Expected: "همهٔ داده‌های IFCDOOR و ..." Received: "All IFCDOOR data and ..."` |

The last row is itself a finding worth recording: an English-only browser assertion cannot
prove the `Entity` term is being *rendered from data* rather than *echoed from
`description`*, because this module's English wording was deliberately written to read
identically to `ifctester`'s own English sentence. Only a non-English request — the API
evidence in §2, and the added `fa-IR` browser context in `report.spec.ts:511` — actually
exercises the code path this task exists to add.

### 8. NOT DONE

Nothing. Both findings in the task's Why section are fixed, proved via `--json`, via the
same document in two languages from the real API, via the real browser (English and
Persian), and via a mutation proof for every new assertion. `services/web/src/i18n/*.json`
received no new entries — noted in §0 with the reason (report prose is server-authored, per
`docs/decisions.md`), not silently skipped.

(§8 is the round-1 self-assessment, left as originally written. The reviewer's F1/F2 findings
below show it was wrong about "nothing" — see §9.)

### 9. Review round 2 (F1, F2, F3) — the fix, and the real path re-run

**F1 fixed.** `_subject_name` (`services/api/cadgpt/apps/review/requirements.py`) now takes
the facet's *value* `comparisons` as a second argument and refuses to render the disjunctive
joiner when both a multi-member restricted name **and** a non-empty value bound are present —
exactly the shape `ifctester`'s `Attribute.__call__` evaluates conjunctively (it iterates
every attribute the restricted name matches and fails on the first that does not satisfy the
bound; source read at `.venv/lib/python3.12/site-packages/ifctester/facet.py:305-384`). The
single-member case is untouched — no joiner, no ambiguity. `requirement_text` now computes
`comparisons` before `name` and threads it through.

**F2 fixed.** `_applicability_facet` (`packages/engine/src/cadgpt_engine/check.py`) now also
drops `name` to `None` whenever `predefinedType` is present but not a literal `str` (a
`Restriction`), so the whole facet falls back to its own `description` — the smallest fix
per the review's own note, not the fuller `predefined_type_comparisons` wire change.

**F3 fixed.** New tests, all failing before the fix and passing after (see the mutation
table below):
- `services/api/cadgpt/apps/review/tests/test_requirements.py`:
  `test_a_restricted_name_with_a_value_bound_falls_back_not_a_false_disjunction` (the
  reviewer's exact repro, as a unit test) and
  `test_a_single_member_restricted_name_with_a_bound_still_renders` (the case the fix must
  not break).
- `packages/engine/tests/test_requirement_basis.py`:
  `test_a_restricted_predefined_type_also_drops_the_literal_name`.

**New fixtures, for the real path rather than only a hand-built `dict`:**
- `packages/engine/tests/fixtures/door_named_bound.ifc` — one door, `GlobalId`
  `3worKcMPzD8x0Y1nJVBqA9`, `OverallHeight=2100`, `OverallWidth=800` — the reviewer's exact
  numbers.
- `packages/engine/tests/fixtures/door_name_restricted_with_bound.ids` — the requirement's
  name restricted to `{OverallWidth, OverallHeight}` **and** a `minInclusive 900` value
  bound on the same facet — the shape F1 fixes.
- `packages/engine/tests/fixtures/door_predefined_type_restricted.ids` — an `Entity`
  applicability facet with `predefinedType` restricted to `{DOOR, GATE}` against
  `three_doors.ifc`, none of whose doors carry a `PredefinedType` at all (0 matched,
  `required` cardinality → FAIL) — the shape F2 fixes. Both added to `SEED_MANIFEST`
  (`services/api/cadgpt/apps/rulepack/management/commands/seed_rule_packs.py`).

**Real path 1 — engine CLI, the reviewer's F1 repro, before contradicting the FAIL beside
it:**

```
$ uv run cadgpt-check packages/engine/tests/fixtures/door_named_bound.ifc \
    packages/engine/tests/fixtures/door_name_restricted_with_bound.ids --json
{
  "status": "FAIL",
  "specifications": [{
    "name": "A recorded overall dimension of at least 900",
    "matched": 1, "status": "FAIL",
    "requirements": [{
      "description": "The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be {'minInclusive': '900'}",
      "basis": {
        "facet_type": "attribute", "name": null, "cardinality": "required",
        "comparisons": [{"operator": "minInclusive", "value": "900"}],
        "name_comparisons": [
          {"operator": "enumeration", "value": "OverallWidth"},
          {"operator": "enumeration", "value": "OverallHeight"}
        ]
      },
      "status": "FAIL",
      "entities": [{"global_id": "3worKcMPzD8x0Y1nJVBqA9", "ifc_class": "IfcDoor",
                    "status": "FAIL", "reason_code": "ATTRIBUTE_VALUE_MISMATCH",
                    "detail": "The attribute value \"800.0\" does not match the requirement"}]
    }]
  }]
}
```

Both `comparisons` and `name_comparisons` are non-empty on the same `basis` — exactly the
ambiguous shape. Feeding that real `basis` into the real, unmodified `requirement_text`
(`DJANGO_SETTINGS_MODULE=cadgpt.config.settings.test`, real `gettext_lazy`/`translation`
machinery, no mocks):

```
en -> The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be {'minInclusive': '900'}
fa -> The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be {'minInclusive': '900'}
```

Both languages now degrade to the (ugly, but never false) `description` fallback instead of
"The OverallWidth or OverallHeight shall be at least 900." — a sentence this exact door,
which FAILs, would satisfy. **Mutation, F1**: with the new
`if len(comparisons) > 1 and value_comparisons: return None` guard in `_subject_name`
removed, the same call reproduces the pre-fix bug verbatim:

```
assert requirement_text(basis, fallback) == fallback
E   assert 'The OverallW...at least 900.' == "The {'enumer...sive': '900'}"
E   - The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be {'minInclusive': '900'}
E   + The OverallWidth or OverallHeight shall be at least 900.
```

`test_a_restricted_name_with_a_value_bound_falls_back_not_a_false_disjunction` fails with
that exact diff; restored afterward, `diff` against a saved copy confirmed byte-identical,
`pytest` green again.

**Real path 2 — engine CLI, the reviewer's F2 repro:**

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc \
    packages/engine/tests/fixtures/door_predefined_type_restricted.ids --json
{
  "status": "FAIL",
  "specifications": [{
    "name": "Named doors and gates only",
    "matched": 0, "status": "FAIL", "reason_code": "NO_SUBJECTS_BUT_REQUIRED",
    "applicability_description": "All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}",
    "applicability_facets": [{
      "facet_type": "entity", "name": null, "predefined_type": null,
      "description": "All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}"
    }]
  }]
}
```

`name` is `null` (post-fix; pre-fix it stayed `"IFCDOOR"`), `matched` is `0` against a model
with three doors, and the specification FAILs — exactly the reviewer's repro. Feeding the
real facet into the real, unmodified `applicability_text`:

```
en -> All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}
fa -> All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}
```

Both languages state the actual restriction (untranslated, correctly — `Entity.
predefinedType` is out of this fix's scope) instead of the false unqualified "All IFCDOOR
data" the pre-fix code rendered. **Mutation, F2**: with `_applicability_facet`'s
`type_restricted` guard removed (back to unconditionally
`name=name if isinstance(name, str) else None`),
`test_a_restricted_predefined_type_also_drops_the_literal_name` fails:

```
assert facet.name is None
E   assert 'IFCDOOR' is None
E    +  where 'IFCDOOR' = ApplicabilityFacet(facet_type='entity', name='IFCDOOR',
        predefined_type=None, description="All IFCDOOR data of type
        {'enumeration': ['DOOR', 'GATE']}").name
```

Restored afterward, `diff` confirmed byte-identical, `pytest` green again.

**Real path 3 — the full HTTP stack, containers rebuilt with the fix.** Both api/worker/beat
images rebuilt from the fixed source (`docker build --network host -f
deploy/docker/api.Dockerfile -t cadgpt-api:latest .`, same `--network host` workaround as
the original evidence's §4; unchanged `Dockerfile`), containers recreated
(`docker compose -f deploy/compose.yaml up -d --no-deps --force-recreate api worker beat`),
`manage.py seed_rule_packs` picked up both new fixtures (`created: Restricted attribute
name with a value bound`, `created: Restricted predefined type applicability`). A real
account, tenant, project, two uploaded models (`door_named_bound.ifc`,
`three_doors.ifc`) and two reviews were created over real HTTP, each `check` queued to the
real Celery worker (`docker logs cadgpt-worker-1`: `check_run_claimed` →
`check_run_pack_evaluated` → `check_run_succeeded`, both `outcome=FAIL` — the same verdicts
as the CLI runs above) and fetched twice, same `run_uuid`, only `Accept-Language` differing:

*F1's review* (`Restricted attribute name with a value bound` against `door_named_bound.ifc`):

```
=== en ===
basis: {"cardinality": "required", "comparisons": [{"operator": "minInclusive", "value": "900"}],
        "facet_type": "attribute", "name": null,
        "name_comparisons": [{"operator": "enumeration", "value": "OverallWidth"},
                              {"operator": "enumeration", "value": "OverallHeight"}]}
requirement_text: The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be {'minInclusive': '900'}

=== fa ===
basis: (byte-identical to en)
requirement_text: The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be {'minInclusive': '900'}
```

*F2's review* (`Restricted predefined type applicability` against `three_doors.ifc`):

```
=== en ===
applicability_facets: [{"description": "All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}",
                         "facet_type": "entity", "name": null, "predefined_type": null}]
applicability_text: All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}

=== fa ===
applicability_facets: (byte-identical to en)
applicability_text: All IFCDOOR data of type {'enumeration': ['DOOR', 'GATE']}
```

Both requests hit `status: succeeded, outcome: FAIL` — matching the CLI. `basis` /
`applicability_facets` are byte-identical across languages in both cases (same stored
document); the rendered fields now state the true, safe fallback in both languages instead
of the false claim, in both languages, from the real HTTP API, real Celery worker, real
Postgres row. The generated Markdown report (`GET .../report-file/`, also re-read from the
rebuilt image) shows the same fallback: `"All IFCDOOR data of type {'enumeration':
['DOOR', 'GATE']}"` under `### Named doors and gates only — Fail`, confirming
`report_markdown.py`'s `applicability_text` read picks up the fix too.

Why the *original* two fixtures' bilingual API proof (§2) was not re-run: neither is
affected by either fix. `door_name_restricted.ids`'s requirement has `comparisons: []`, so
F1's new guard (`len(comparisons) > 1 and value_comparisons`) never trips. Both facets in
`door_width_named_applicability.ids`'s applicability have a literal or absent
`predefinedType` (never a `Restriction`), so F2's new guard never trips either. The full
`pytest` suite (284 passed, up from 281 — the 3 new tests, nothing removed or reworded) is
the regression check for those two cases, not a second live bilingual round-trip.

**`make verify`, after the fix** (same commands as §3; `msgfmt`/`GNU gettext-tools` had to
be put on `PATH`/`LD_LIBRARY_PATH` from a pre-extracted archive in this sandbox — an
environment gap unrelated to this change, `compilemessages` itself reports the catalogue
already compiled and up to date):

```
$ make verify
uv run ruff check .                        All checks passed!
uv run ruff format --check .                189 files already formatted
uv run mypy packages/engine/src services/api/cadgpt   Success: no issues found in 172 source files
uv run lint-imports --no-cache              Contracts: 5 kept, 0 broken.
uv run pytest                               284 passed, 34 warnings in 6.63s
cd services/web && pnpm run verify          lint (1 pre-existing warning, unrelated) /
                                             typecheck / build / storybook build /
                                             test-unit (2 passed) / test-storybook (35 passed)
                                             all clean
```

Exit code `0`.

**Wiring, round 2.** `SEED_MANIFEST` (`services/api/cadgpt/apps/rulepack/management/
commands/seed_rule_packs.py`) now includes both new fixtures — confirmed `created` (not
`skipped`) in the seed run above, and both packs were fetched from the live
`/api/v1/rule-packs/` catalogue before being cited by UUID in the two reviews' `check`
calls, the same registration path every other seeded pack already uses.

**NOT DONE, round 2.** The full Playwright `make e2e` suite and a browser screenshot were
not re-run for these two new fixtures specifically — §5's existing 11 specs (including the
two T-0039 added in round 1) all still pass under `make verify`'s `pytest`/`vitest`/
`storybook` gates, and the fix is proven over the real HTTP + Celery + Postgres stack in
§9's "Real path 3" instead, which is what actually changed. A pre-existing, unrelated
`makemigrations --check` drift on `review.checkrun.failure_reason` (`Alter field
failure_reason on checkrun`) was noticed while migrating the rebuilt containers; `migrate`
itself applies cleanly (nothing pending), it is not caused by this task's changes, and it is
left alone rather than folded into this commit.

## Review

**Verdict: fix now, same task.** The reviewer independently re-derived the bilingual claim
(different documents, same live database, same result), traced backward compatibility for
real against actually-stored schema 1/2/3 runs rather than trusting the docstrings, and
confirmed the gettext joiner reuse, the `name`/`name_comparisons` exclusivity, and the
`ifctester` template fidelity are all genuinely correct. Two findings are I5 violations —
both make a citation state something the underlying IDS did not establish, which this task
is gated on:

- **F1.** `_subject_name` (`requirements.py:100-104`) always joins `name_comparisons` with
  the disjunctive `" or "`, which is only correct when the facet's value `comparisons` are
  empty (an existence check — "one of these attributes must be provided"). The moment the
  same facet also carries a value bound, `ifctester`'s own `Attribute.__call__` evaluates
  every matching attribute conjunctively and fails on the first mismatch — so a restricted
  name plus a bound is an AND, and the shipped code prints an OR. Reviewer's live repro: a
  door with `OverallHeight = 2100` (satisfies "at least 900") and `OverallWidth = 800`
  (does not) is reported FAIL with the sentence "The OverallWidth or OverallHeight shall be
  at least 900" — a sentence the door satisfies, contradicting the FAIL beside it. Before
  this task the same case fell back to the dict repr: ugly, but never a false claim. This
  task made it false.
- **F2.** `_applicability_facet` (`check.py`) collapses a restricted (non-literal)
  `predefinedType` to `None`, which `_facet_text` (`applicability.py`) cannot distinguish
  from "no `predefinedType` stated at all" — so a specification whose applicability is
  genuinely narrowed to `predefinedType ∈ {DOOR, GATE}` renders "All IFCDOOR data" (no
  restriction stated) instead of naming the restriction. Reviewer's live repro: such a
  specification matches 0 real elements and FAILs, but the printed line claims to cover
  every `IFCDOOR`, reading as "a rule about all doors found none" in a model with three.
- **F3.** No test can catch F1: every new `name_comparisons` test and both new fixtures seed
  `"comparisons": []` — exactly the one shape where the disjunctive rendering is correct.
  The feature's only wrong case is the one nothing exercises.

Sent back to the same builder per `docs/agents.md` ("Fix now — same task, same builder, no
new review afterward"). Three non-blocking observations recorded for the judge, not acted on
here: **F4**, a restricted `Entity` *name* in an applicability facet still renders the
Python dict repr as the primary applicability line — pre-existing (not introduced by this
task), the same defect class this task's own Why section names, now surviving on the field
this task rewrote, with a test asserting it as correct; **F5**, `_subject_name`'s `"literal"`
branch is unreachable from any real engine output and a test exercises it anyway; **F6**, the
pre-existing dirty `.gitignore` and untracked `cadgpt-logo.svg` remain unrelated to this task
and must not be swept into its commit.
