# T-0027 — The requirement a finding cites, as structured data the service can localize

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** I5 — every finding cites a resolvable basis. Also `CLAUDE.md`'s
gettext rule. **The reviewer will be dispatched on this task.**

## Why

T-0026 replaced a CPython object address with `ifctester`'s own sentence, which was the right
move and is strictly better. But the reviewer of that task established three things about what
now reaches the screen, and they share one root:

```
The OverallWidth shall be {'minInclusive': '900'}
```

**It is English prose, and it is the report's primary user-facing line.** The service's own
`services/api/cadgpt/apps/review/services/presentation.py` states the design in its first
line: the document in the database holds reason codes and no prose, and the service supplies
the wording, so one stored run reads in Persian and in English from the same document. That is
why `reason_label` exists beside `reason_code`. `requirement.description` now bypasses it
entirely — English is written into the stored document by the engine and rendered straight to
the DOM at `ReportView.tsx:62`. `CLAUDE.md` states the gettext rule without exception, and the
tenants are multinational. T-0026 did not create this gap, but it made it load-bearing: the
line an architect reads first is the one line that cannot be translated.

**The value is a Python dict repr, and it carries no unit.** `{'minInclusive': '900'}` rather
than "at least 900 mm", while the failing row beside it reports a bare `800.0`. The reviewer
confirmed this is upstream's unmodified output — `Restriction.__str__` at
`ifctester/facet.py:1085` returns `str(self.options)` — so there is no upstream rendering
being bypassed and no amount of calling `to_string` differently will fix it. `prd.md` 5.7
requires every finding to report measured against required with its margin; a dict and a bare
float are neither.

**The report never states what a rule applies to.** ifctester renders applicability facets —
`reporter.py:296` produces `All IFCDOOR data` — and we drop them. Our own fixture ships an
empty `<ids:description>`, so `spec.description` is `""` and nothing in the output names the
subject set at all. Under I5 a requirement without its subject is half a citation: "shall be
at least 900" is not a basis until it says what shall be.

## Scope

The shape of the fix is the shape `reason_code` / `reason_label` already established, extended
from the reason to the requirement. The engine names things; the service supplies the wording.

**Changes**

- `packages/engine/src/cadgpt_engine/report.py` — `RequirementOutcome` gains a structured
  counterpart to `description`: the facet type, the attribute or property name, the
  cardinality, and the bound as a comparison it can be rendered from — the operator
  (`minInclusive`, `maxInclusive`, `enumeration`, a literal, …) and the value, not a stringified
  dict. Types at module boundaries; `mypy --strict` passes. This is a wire-format change, so
  **bump `REPORT_SCHEMA_VERSION`** — unlike T-0026, a field is changing meaning here, and the
  constant's own docstring says that is exactly when to bump.
- `packages/engine/src/cadgpt_engine/check.py` — populate it. The data is on the facet
  already; read it rather than parsing `to_string`'s output back apart, which would be
  building a parser for a string we generated.
- **Keep `description`.** It is upstream's sentence, it is what the engine's CLI and tests
  print, and the engine cannot translate. It becomes the fallback, not the primary.
- `services/api/cadgpt/apps/review/` — the service renders the requirement into the reader's
  language through `gettext`, beside the existing reason wording. Follow whatever
  `presentation.py` and `reasons.py` already do for `reason_label`; do not invent a second
  mechanism next to it.
- `services/web/` — render the localized requirement, falling back to `description` when the
  structured form is absent, so reports stored before the schema bump still read.
- **The subject.** Carry the applicability rendering through as well, so the report states what
  the rule applies to. `to_string("applicability", specification)` is the inherited call.
  Whether that is a new field on `SpecificationOutcome` or a use of the existing empty
  `description` is yours; if you use `description`, say why in the evidence, because it
  currently means the IDS author's own `<ids:description>` text and overwriting that would be
  discarding something a rule author wrote.

**What explicitly does not change**

- Units are not invented. If the IDS does not state a unit, the report does not state one —
  `CLAUDE.md`'s measure-never-invent applies to the citation as much as to the measurement. If
  the unit is recoverable from the IFC's own unit assignment, that is measurement and is in
  scope; if it is not there, the report says the bound without a unit rather than guessing mm.
- Margin — the signed distance between measured and required — is `prd.md` 5.7 and is **not**
  this task. This task makes the requirement citable; margin needs a tolerance policy per rule,
  which the rule layer does not have yet.
- No new engine abstraction beyond the dataclass fields. One facet type is enough to ship this;
  do not build a renderer registry for facet types the fixtures do not exercise.

## Sequencing note — added 2026-09-02 by the coordinator

**T-0037 lands immediately after this task and touches the same three places**:
`RequirementOutcome`, `presentation.py`, and the requirement's rendering in `ReportView.tsx`.
It carries a `reason_code` down to the requirement so that a row which evaluated nothing says
*why*, and it puts a `StatusPill` beside the requirement description — `requirement.status` is
currently read by no component at all, which is why T-0028's fix is invisible in the browser.

Shape the dataclass and the localization path to receive that field, so it is added rather than
restructured. **Do not implement T-0037 here** — it is a separate task with its own review, and
widening this one is how a task stops being finishable. If a choice in this task would make
T-0037 awkward, note it in the evidence rather than pre-building for it.

## How to prove it ran

```sh
uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc \
                           packages/engine/tests/fixtures/door_width.ids --json
make verify
make up
make e2e
```

The evidence must show:

1. The `--json` output with the structured requirement fields populated, pasted whole for the
   one specification, showing the bound as an operator and a value rather than a stringified
   dict.
2. **The same run rendered in two languages.** This is the assertion that proves the gettext
   path exists rather than being described: fetch the run detail for a tenant whose language
   is English and again for Persian, and paste both requirement lines from the API response.
   One stored document, two renderings. A single-language output does not prove this task.
3. The report naming what the rule applies to — the subject line, from the browser.
4. `make verify` passing, and `REPORT_SCHEMA_VERSION` bumped with a test that a document at
   the previous version still deserializes and renders through the fallback.
5. `make e2e` passing with an assertion on the localized requirement text, and a refreshed
   screenshot you have opened.
6. **Wiring:** quote the `gettext` call site that produces the requirement wording, and the
   line in the serializer that puts it on the response.

## Evidence

### 1. `--json` output, one specification, the bound as data

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc \
                       packages/engine/tests/fixtures/door_width.ids --json
{
  "schema_version": 2,
  "engine_version": "0.1.0",
  "ifc_filename": "three_doors.ifc",
  "ifc_schema": "IFC4",
  "ids_title": "Accessible door width",
  "status": "FAIL",
  "specifications_passed": 0,
  "specifications_failed": 1,
  "specifications_indeterminate": 0,
  "passed": 1,
  "failed": 1,
  "indeterminate": 1,
  "specifications": [
    {
      "name": "Minimum clear door width 900 mm",
      "description": "",
      "applicability_description": "All IFCDOOR data",
      "instructions": "",
      "applicability": "APPLIES",
      "status": "FAIL",
      "cardinality": "required",
      "matched": 3,
      "reason_code": null,
      "passed": 1,
      "failed": 1,
      "indeterminate": 1,
      "requirements": [
        {
          "description": "The OverallWidth shall be {'minInclusive': '900'}",
          "basis": {
            "facet_type": "attribute",
            "name": "OverallWidth",
            "cardinality": "required",
            "comparisons": [
              {
                "operator": "minInclusive",
                "value": "900"
              }
            ]
          },
          "status": "FAIL",
          "passed": 1,
          "failed": 1,
          "indeterminate": 1,
          "entities": [
            {
              "global_id": "3worKcMPzD8x0Y1nJVBqA2",
              "ifc_class": "IfcDoor",
              "status": "FAIL",
              "reason_code": "ATTRIBUTE_VALUE_MISMATCH",
              "detail": "The attribute value \"800.0\" does not match the requirement"
            },
            {
              "global_id": "3worKcMPzD8x0Y1nJVBqA3",
              "ifc_class": "IfcDoor",
              "status": "INDETERMINATE",
              "reason_code": "ATTRIBUTE_EMPTY",
              "detail": "The attribute value \"None\" is empty"
            }
          ],
          "entities_omitted": 0
        }
      ]
    }
  ]
}
```

`description` is unchanged (still upstream's dict-repr sentence, kept as the fallback).
`basis.comparisons` is the operator/value pair a service renders from, and
`applicability_description` is the subject the report previously dropped.

### 2. The same run, two languages — one stored document, two renderings

Registered a real account and tenant, uploaded `door_width.ids` and `three_doors.ifc`,
created a review, and ran a real check through the full HTTP stack (`docker compose`, not
`make e2e` for this step — this is the API directly, proving the localization path
independent of the browser). Same `run_uuid`, same stored `report` document, fetched twice
with a different `Accept-Language` header:

```
$ curl -s http://localhost:8000/api/v1/reviews/$REVIEW/runs/$RUN/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: $TENANT" -H "Accept-Language: en"
applicability_description: All IFCDOOR data
description: The OverallWidth shall be {'minInclusive': '900'}
requirement_text: The OverallWidth shall be at least 900.
basis: {"name": "OverallWidth", "facet_type": "attribute", "cardinality": "required",
        "comparisons": [{"value": "900", "operator": "minInclusive"}]}

$ curl -s http://localhost:8000/api/v1/reviews/$REVIEW/runs/$RUN/ \
    -H "Authorization: Bearer $TOKEN" -H "X-Tenant: $TENANT" -H "Accept-Language: fa"
applicability_description: All IFCDOOR data
description: The OverallWidth shall be {'minInclusive': '900'}
requirement_text: OverallWidth باید دست‌کم 900 باشد.
```

`description` and `basis` are identical in both responses (the stored document did not
change); `requirement_text` is the only field that differs, and it differs because of the
`Accept-Language` header alone -- the gettext path, not a re-run of the engine.

### 3. The subject line, from the browser

Screenshot (`services/web/e2e/screenshots/report.png`, refreshed by the `make e2e` run
below) shows, under "Minimum clear door width 900 mm":

```
All IFCDOOR data
The OverallWidth shall be at least 900.
```

`applicability_description` ("All IFCDOOR data") is ifctester's own applicability
rendering, carried through as-is -- **not** run through gettext. `spec.description` (the
IDS author's own `<ids:description>`) was left alone rather than overwritten, per the
task's instruction to say why if `description` is reused: it wasn't reused, a new field was
added instead, specifically so the author's own text is never at risk of being replaced by
engine-generated text. `applicability_description` itself stays English because rendering
it into a sentence per facet type (`Entity` here) is exactly the renderer registry this
task's scope forbids building for a facet type beyond the one the fixtures exercise
(`Attribute`); it is carried through untranslated the same way `instructions` and the IDS
`description` already are.

### 4. `make verify` and the schema-bump safety net

```
$ make verify
uv run ruff check .                        All checks passed!
uv run ruff format --check .                155 files already formatted
uv run mypy packages/engine/src services/api/cadgpt   Success: no issues found in 141 source files
uv run lint-imports --no-cache              Contracts: 5 kept, 0 broken.
uv run pytest                               183 passed, 18 warnings in 2.86s
cd services/web && pnpm run verify          lint / typecheck / build all clean
```

`REPORT_SCHEMA_VERSION` bumped 1 -> 2 (`packages/engine/src/cadgpt_engine/report.py`), with
the reasoning in its own docstring: `description`'s *role* changes from citation to
fallback even though its text does not.

Fallback safety is proven at two levels:

- `packages/engine/tests/test_requirements.py::test_a_document_stored_before_basis_existed_falls_back_to_description`
  -- `requirement_text(None, old_description) == old_description`.
- `services/api/cadgpt/apps/review/tests/test_presentation.py::test_a_v1_schema_document_still_localizes_through_the_fallback`
  -- a hand-built dict shaped exactly like `REPORT_SCHEMA_VERSION` 1's own `to_dict()`
  output (no `basis` key, no `applicability_description` key at all) is passed through
  `localize_report()` end to end and renders `requirement_text` via the fallback without
  raising.

### 5. `make e2e` passing, with an assertion on the localized text

```
$ make e2e
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (10.1s)
  1 passed (11.3s)
```

`services/web/e2e/report.spec.ts` now asserts, from the real running stack:

```ts
const requirementText = report.locator('[data-testid="requirement-text"]');
await expect(requirementText).not.toContainText("object at 0x");
await expect(requirementText).toHaveText("The OverallWidth shall be at least 900.");
await expect(requirementText).not.toContainText("minInclusive");

const applicability = report.locator('[data-testid="applicability"]').first();
await expect(applicability).toHaveText("All IFCDOOR data");
```

Screenshot at `services/web/e2e/screenshots/report.png` was opened and shows the coverage
band, the subject line ("All IFCDOOR data"), the localized requirement line ("The
OverallWidth shall be at least 900."), and the still-bare measured value ("800.0") in the
entity row beside it.

### 6. Wiring

The `gettext` call site producing the requirement wording
(`services/api/cadgpt/apps/review/requirements.py:46` for the template, used at
`requirements.py:94-95`):

```python
_REQUIRED_WITH_BOUND = _("The %(name)s shall be %(bound)s.")
...
    if bound:
        return str(template) % {"name": name, "bound": bound}
    return str(template) % {"name": name}
```

The line in the serializer path that puts it on the response
(`services/api/cadgpt/apps/review/services/presentation.py:37-39`, called from
`services/api/cadgpt/apps/review/api/v1/serializers.py:64-65`):

```python
# presentation.py
"requirement_text": requirement_text(
    requirement.get("basis"), requirement.get("description", "")
),

# serializers.py -- CheckRunDetailSerializer
def get_report(self, obj: CheckRun) -> dict[str, Any] | None:
    return localize_report(obj.report)
```

### Mutation proofs

Each new load-bearing assertion was proven load-bearing: revert the fix, run the real test,
see it fail with real error text, restore, see it pass again. All reverts were confirmed
byte-identical to the pre-mutation file afterward (`diff` against a backup).

1. **`_comparisons` (the operator/value extraction).** Mutated to `return ()`. Failed:
   `test_the_requirement_basis_names_the_bound_as_data_not_a_stringified_dict` --
   `AssertionError: assert () == (Comparison(...value='900'),)` -- and three tests in
   `test_requirement_basis.py`. Restored; all four pass again.
2. **The `maxOccurs == 0` cardinality substitution.** Mutated to always use the facet's own
   `cardinality`. Failed:
   `test_a_prohibited_specifications_requirement_line_never_contradicts_its_verdict` --
   `AssertionError: assert 'required' == 'prohibited'`. Restored; passes again.
3. **`applicability_description` population.** Mutated to `""`. Failed:
   `test_the_specification_states_what_it_applies_to` --
   `AssertionError: assert '' == 'All IFCDOOR data'`. Restored; passes again.
4. **`requirement_text`'s rendering (service).** Mutated to `return fallback`
   unconditionally. Failed 4 of 6 tests in `test_requirements.py` (the two that already
   expect the fallback did not, correctly). Example:
   `AssertionError: assert 'fallback' == 'The Name shall be provided.'`. Restored; all six
   pass again.
5. **The v1-document fallback in `presentation.py`.** Mutated
   `requirement.get("basis")` to `requirement["basis"]`. Failed:
   `test_a_v1_schema_document_still_localizes_through_the_fallback` -- `KeyError: 'basis'`,
   raised from `presentation.py:38` exactly where the mutation was. Restored; passes again.
6. **The DOM wiring (`data-testid="requirement-text"`).** Reverted `ReportView.tsx` to the
   pre-task render (`{requirement.description}`, no `data-testid`), rebuilt the `web`
   container, ran `make e2e`. Failed: `Error: element(s) not found` on
   `locator('[data-testid="requirement-text"]')` at `report.spec.ts:111`. Restored,
   rebuilt, `make e2e` passed again (see section 5).

### Not done / scope notes

- **Property facets are not rendered into a sentence**, even though the engine names a
  `Property` facet's `baseName` in `basis.name` exactly like an `Attribute`'s. The service's
  `requirement_text` only renders `facet_type == "attribute"`; a `Property` requirement
  falls back to `description`. No fixture exercises a `Property` facet, and `Property`'s own
  sentence shape ("`{baseName}` data shall be `{value}` and in the dataset `{propertySet}`")
  needs `propertySet`, which `RequirementBasis` does not carry -- adding it without a
  fixture to prove it against would be exactly the untested renderer-registry expansion the
  task's scope forbids. This is a real, stated gap, not a silent one.
- **Multi-comparison rendering was implemented and shipped with a real defect the original
  evidence block misdescribed as covered.** The claim that
  `test_an_enumeration_restriction_...` was "the closest real case" was false: that test
  (`packages/engine/tests/test_requirement_basis.py`) asserts `_comparisons`' output inside
  the *engine* -- the data shape -- and never calls the *service*'s `_bound`/`requirement_text`,
  which is where the actual bug lived (an `xs:enumeration` disjunction rendered with the
  conjunctive "and" joiner, `The Name shall be D-01 and D-02.`; see the Review section's F1
  and "Fix-now evidence" below for the reproduction and the fix). The corrected version now
  has a real test of the rendered sentence for both the disjunctive case
  (`test_an_enumeration_becomes_a_disjunction_not_a_conjunction`) and the conjunctive case
  (`test_a_range_with_two_bounds_stays_a_conjunction`), and both are exercised against the
  real API in both languages in "Fix-now evidence". No shipped `.ids` fixture under
  `packages/engine/tests/fixtures/` produces either shape on its own -- the two IDS files used
  for that real-path proof live only in the evidence, not the fixture directory -- so the
  engine-level `RequirementBasis` extraction for a multi-comparison bound still has no
  integration-level engine test, only the service-level rendering does.
- T-0037 was not implemented. Per the sequencing note, the dataclass and localization path
  were shaped to receive a `reason_code` and a `StatusPill` addition without restructuring:
  `RequirementBasis` and `requirement_text`'s signature both take/return plain data, so
  T-0037 can add a field and a template branch without touching what this task shipped.

## Review

**Verdict: the mechanism is right and two of the sentences it produces are false.** Reviewed on
opus, gated on I5 and the gettext rule.

The design is sound and was confirmed rather than assumed: the engine names the citation as
data, the service supplies the wording, `description` remains the fallback, and the coordinator
verified one stored document rendering `The OverallWidth shall be at least 900.` in English and
`OverallWidth باید دست‌کم 900 باشد.` in Persian, with a hand-built v1 document still rendering
through the fallback in both locales. `applicability_description` puts `All IFCDOOR data` on
screen, so a requirement finally states what it applies to.

Seven suspicions were raised and dropped after execution, recorded so nobody pays for them
twice: format-string injection through an IDS value does not survive (`%` only ever appears in
the substitution position — a value of `100%(name)s` renders literally); XSS does not survive
(the string reaches JSX and is escaped, and there is no `dangerouslySetInnerHTML` anywhere in
`services/web/src`); no unit, rounding or coercion is ever introduced (`_comparisons` does
`str(m)` on what `ifctester` parsed and nothing else — floats, negatives and `۹۰۰` pass through
unchanged); no lazy string is stored or serialised; all 16 new msgids are present in the fa
catalogue with non-empty translations and none falls through to English; nothing anywhere
branches on `schema_version`, and the fallback keys off field presence, which is the more robust
choice, so no migration is owed; and dropping the `specification` argument from
`to_string("applicability")` is an undisclosed deviation from this task's text but is *correct*
— passing it swaps upstream to `prohibited_templates`, which would put "Shall not be IFCDOOR
data" in the subject slot, and the builder's form matches upstream's own `reporter.py:296`.

The mutation spot-check was re-run by the reviewer on the least obvious of the six claims (the
`maxOccurs == 0` cardinality substitution) and reproduced exactly: `AssertionError: assert
'required' == 'prohibited'` at `test_check.py:146`, restored, identical, passing.

### FIX NOW — two findings, both I5, both confirmed by the coordinator on the real path

**F1. An `enumeration` restriction is rendered as a conjunction, so the report states a rule the
IDS does not state.** `services/api/cadgpt/apps/review/requirements.py:67` joins every
comparison with `_JOINER = _(" and ")`, unconditionally. IDS `xs:enumeration` is a
**disjunction** — the value must be *one of* the members. Reproduced:

```
enumeration (disjunction)  -> The Name shall be D-01 and D-02.
range (conjunction)        -> The Name shall be at least 900 and at most 1200.
```

The second is correct. The first tells the architect the attribute must equal both values at
once, which no model can satisfy and no IDS ever asked for. This is I5 failing in the way that
matters most — not an unresolvable citation, but a resolvable one that resolves to the wrong
rule.

**It also falsifies the evidence block.** The "Not done / scope notes" bullet says multi-
comparison joining is "implemented but not exercised by any fixture… `test_an_enumeration_
restriction_...` covers multiple *enumeration* members, which is the closest real case." The
closest real case is precisely the case where the joiner is wrong, and that test only asserts
`_comparisons`' output inside the engine — it never runs the joiner. The declared gap is real;
the reassurance attached to it is not.

**F2. An operator the table does not recognise is dropped, and the bare value is asserted as the
bound.** `requirements.py:63` falls back to `"%(value)s"`. Reproduced:

```
unknown operator (totalDigits) -> The Name shall be 4.
```

The IDS said "at most 4 significant digits". `totalDigits` and `fractionDigits` are in
`ifctester`'s own supported constraint list (`facet.py:1036-1037`), so this is reachable from
valid IDS today, and `whiteSpace` and `assertion` behave the same way. The module docstring
claims this is "the same 'never nothing' degrade `reasons.label_for` makes for an unknown
`ReasonCode`". It is not the same, and the difference is the whole point: `label_for` degrades
to the **identifier**, which is visibly unresolved and honest; this degrades to a **confidently
wrong sentence** indistinguishable from a correct one. Under measure-never-invent the correct
degrade is the `description` fallback, or the operator rendered verbatim — never the value
alone.

### Fix-now round — what the builder must land

1. **Group `enumeration` members and join them as a disjunction**, through `gettext`, in both
   catalogues. A range keeps its "and". Do not special-case by counting comparisons — key off
   the operator, because that is the thing that actually decides whether the join is a
   conjunction or a disjunction.
2. **An unrecognised operator must not produce a confident sentence.** Fall back to
   `description`, or render the operator name verbatim beside its value. Correct the module
   docstring's `reasons.label_for` parity claim in the same edit — it is what made this look
   safe.
3. **A test per case, on the real path**, and both must fail with the fix reverted. The
   enumeration case in particular must assert the rendered *sentence*, not `_comparisons`'
   output — asserting the engine's data is what let this ship.

### QUEUED — T-0039 and T-0040

Finding 3 (a restriction on the attribute *name* leaves `basis.name` null and puts
`The {'enumeration': ['OverallWidth', 'OverallHeight']} shall be provided` back in the primary
line — the exact dict repr this task exists to eliminate, reachable because `Facet.parse` is
generic and turns *any* parameter into a `Restriction`) and finding 4
(`applicability_description` is untranslated English written into the stored document by the
engine and rendered straight to the DOM — verbatim the defect this task's own "Why" section
opens with, reintroduced on a new field, with `" and "` hardcoded in the engine as its joiner)
are the same subject, and became **T-0039**. Finding 5 (`localize_report` raises `KeyError`,
`TypeError` or `AttributeError` on a malformed `basis`, 500-ing the whole run-detail response
where `label_for` is total by construction) became **T-0040**.

## Fix-now evidence

Both findings fixed in `services/api/cadgpt/apps/review/requirements.py`:

- `_bound` now groups `enumeration` members and joins them with a new `_ENUMERATION_JOINER =
  _(" or ")` (disjunction); every other comparison still joins with `_JOINER = _(" and ")`
  (conjunction). Which joiner applies is decided by checking each comparison's `operator`,
  never by counting how many comparisons there are.
- A new `_recognised(comparisons)` check runs before any sentence is built. If any
  comparison's operator is not a key in `_COMPARISON_TEMPLATES`, `requirement_text` returns
  `fallback` (`description`) immediately -- no sentence is attempted, confident or otherwise.
- The module docstring's false parity claim ("the same 'never nothing' degrade
  `reasons.label_for` makes for an unknown `ReasonCode`") is corrected to state the actual,
  different degrade: `label_for` falls back to the bare identifier (visibly unresolved);
  this module falls back to `description` (the real sentence, in English) rather than to a
  confident sentence for the wrong rule.
- The "Not done / scope notes" bullet on multi-comparison rendering (above) is rewritten to
  say what was actually true: the claim that `test_an_enumeration_restriction_...` was "the
  closest real case" was false -- that test asserts the engine's data shape and never runs
  the service's joiner, which is exactly where the bug lived.

### `make verify`

```
$ make verify
uv run ruff check .                                    All checks passed!
uv run ruff format --check .                            168 files already formatted
uv run mypy packages/engine/src services/api/cadgpt     Success: no issues found in 141 source files
uv run lint-imports --no-cache                          Contracts: 5 kept, 0 broken.
uv run pytest                                            186 passed, 18 warnings in 2.85s
cd services/web && pnpm run verify                       lint / typecheck / build all clean
```

### Mutation proofs (both reverted, run, restored, diffed byte-identical afterward)

**F1 -- the enumeration/conjunction split.** Reverted `_bound` to the original unconditional
join (`str(_JOINER).join(...)` over every comparison, no enumeration grouping):

```
$ uv run pytest services/api/cadgpt/apps/review/tests/test_requirements.py::test_an_enumeration_becomes_a_disjunction_not_a_conjunction -q
FAILED test_requirements.py::test_an_enumeration_becomes_a_disjunction_not_a_conjunction
    assert requirement_text(basis, "fallback") == "The Name shall be D-01 or D-02."
E   AssertionError: assert 'The Name sha...-01 and D-02.' == 'The Name sha...D-01 or D-02.'
E     - The Name shall be D-01 or D-02.
E     ?                        ^^
E     + The Name shall be D-01 and D-02.
E     ?                        ^^^
```

Restored; `diff` against the pre-mutation backup: identical. Suite passes again (9/9 in
`test_requirements.py`).

**F2 -- the unrecognised-operator guard.** Reverted `requirement_text` to skip the
`_recognised` check and reverted `_bound` to degrade an unknown operator to a bare
`"%(value)s"` template (the original shape, both changes together, to reproduce the exact
originally-reported bug rather than a different failure mode):

```
$ uv run pytest services/api/cadgpt/apps/review/tests/test_requirements.py::test_an_unrecognised_operator_falls_back_to_description -q
FAILED test_requirements.py::test_an_unrecognised_operator_falls_back_to_description
    assert (
        requirement_text(basis, "the real ifctester sentence")
        == "the real ifctester sentence"
    )
E   AssertionError: assert 'The Name shall be 4.' == 'the real ifctester sentence'
E     - the real ifctester sentence
E     + The Name shall be 4.
```

Restored; `diff` against the pre-mutation backup: identical. Suite passes again (9/9 in
`test_requirements.py`).

### Real path: an enumeration IDS and an unknown-operator IDS, in both languages

Two new `.ids` files (not committed -- these are evidence-only, run through the real engine
and the real HTTP stack against the existing `three_doors.ifc` fixture, whose doors are
named `wide`, `narrow`, `unknown`):

`door_name_enumeration.ids` -- `Name` restricted to `xs:enumeration` values `wide`, `narrow`:

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc door_name_enumeration.ids --json
"description": "The Name shall be {'enumeration': ['wide', 'narrow']}",
"basis": {
  "facet_type": "attribute", "name": "Name", "cardinality": "required",
  "comparisons": [
    {"operator": "enumeration", "value": "wide"},
    {"operator": "enumeration", "value": "narrow"}
  ]
}
```

`door_width_total_digits.ids` -- `OverallWidth` restricted to `xs:integer` with
`xs:totalDigits value="4"` (a real, XSD-valid restriction `ifctester.facet.Restriction`
parses and stores under the key `"totalDigits"`, which this module's `_COMPARISON_TEMPLATES`
does not have an entry for):

```
$ uv run cadgpt-check packages/engine/tests/fixtures/three_doors.ifc door_width_total_digits.ids --json
"description": "The OverallWidth shall be {'totalDigits': 4}",
"basis": {
  "facet_type": "attribute", "name": "OverallWidth", "cardinality": "required",
  "comparisons": [{"operator": "totalDigits", "value": "4"}]
}
```

Both run through a real account, tenant, upload, review and check via the live API
(`docker compose -f deploy/compose.yaml up -d --build web` rebuilt `web`, `api` and `worker`
first, picking up the fix), then fetched twice each with a different `Accept-Language`
header -- same stored `report` document both times, only the header differs:

```
$ curl .../runs/$ENUM_RUN/ -H "Accept-Language: en"
description: The Name shall be {'enumeration': ['wide', 'narrow']}
requirement_text: The Name shall be wide or narrow.

$ curl .../runs/$ENUM_RUN/ -H "Accept-Language: fa"
description: The Name shall be {'enumeration': ['wide', 'narrow']}
requirement_text: Name باید wide یا narrow باشد.

$ curl .../runs/$DIGITS_RUN/ -H "Accept-Language: en"
description: The OverallWidth shall be {'totalDigits': 4}
requirement_text: The OverallWidth shall be {'totalDigits': 4}

$ curl .../runs/$DIGITS_RUN/ -H "Accept-Language: fa"
description: The OverallWidth shall be {'totalDigits': 4}
requirement_text: The OverallWidth shall be {'totalDigits': 4}
```

The enumeration case now reads as a disjunction in both languages ("or" / "یا"). The
`totalDigits` case falls back to `description` verbatim -- identical text in both language
responses, which is correct: `description` is `ifctester`'s own English sentence and this
module has nothing to translate when it refuses to render a sentence of its own.

Before rebuilding the containers, the same two runs were fetched against the still-running
pre-fix image and reproduced the exact bugs reported: `The Name shall be wide and narrow.`
(conjunction for a disjunctive restriction) and `The OverallWidth shall be 4.` (a confident
wrong sentence for `totalDigits`) -- the real path carrying the same defect the reviewer
found by inspection.

### `make e2e`

Ran after rebuilding `web` (`docker compose -f deploy/compose.yaml up -d --build web`) with
the fix in place:

```
$ make e2e
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/report.spec.ts:40:1 › a real check run reproduces 1 pass / 1 fail / 1 indeterminate in the browser (10.5s)
  1 passed (11.8s)
```

The existing browser assertions (`The OverallWidth shall be at least 900.`, `All IFCDOOR
data`) are unaffected by this fix -- `door_width.ids`'s single `minInclusive` comparison
takes neither the new disjunction branch nor the new unrecognised-operator branch, which is
exactly why F1 and F2 needed their own real-path fixtures rather than being provable through
the existing e2e spec alone.
