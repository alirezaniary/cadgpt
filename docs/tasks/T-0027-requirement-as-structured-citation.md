# T-0027 — The requirement a finding cites, as structured data the service can localize

**Phase:** 3 — What the first real user needs   **Status:** open
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

<!-- the builder writes this -->

## Review
