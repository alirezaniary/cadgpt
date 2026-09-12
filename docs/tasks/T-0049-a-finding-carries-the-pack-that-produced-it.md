# T-0049 — Every finding carries the pack identity and version that produced it

**Phase:** 3   **Status:** done
**Touches invariants:** I5 (a finding cites its authority), "never assert compliance we did not
establish". **Reviewer-gated.**

## Why

Found by the T-0031 review. `prd.md` §5.7 is explicit: *every finding carries the pack identity
and version, because a finding asserts that a rule says something, under our name.*

T-0031's `_combine_reports` flattens every selected pack's specifications into one tuple with no
pack attribution, and `ReportView.tsx` renders them as one list. The selection appears as a block
at the top of the report, so the run says *which packs it ran*; an individual finding cannot be
traced back to the pack — or to that pack's `source_citation` — that produced it.

T-0031's Scope only promised "the run's recorded selection shown on the report", so the code is
scope-honest and the review said so. It is the *Why* that over-claimed, and this task is the part
that was actually promised by the PRD and not delivered. It matters most exactly where the
product is most exposed: a FAIL that an architect forwards to a client is an assertion that some
named rule, from some named source, says the thing. Right now the report can say which packs were
in the room; it cannot say which one spoke.

This is also what makes `RulePack.source_citation` (T-0030) reachable. Today it is a column with
real attribution in it that no report surface ever renders.

## Scope

**Changes**

- A specification in a combined report carries the identity of the pack it came from — uuid,
  name and version at minimum, sufficient to resolve to the recorded selection entry rather than
  duplicating it.
- The report surface renders that attribution on the finding, and reaches the pack's
  `source_citation` from it.
- The Markdown report (T-0032) carries it too. If T-0032 has landed by the time this is built,
  it is in scope here; if not, T-0032's task file gains the requirement.
- `REPORT_SCHEMA_VERSION` bump, and the fallback for documents stored before it, following the
  pattern T-0027 established: the fallback keys off field presence, not version number.

**What explicitly does not change**

- The engine. It checks one IDS file per call and does not know what a `RulePack` is; the
  attribution is applied where the several reports become one, in the service layer.
- The counts, the coverage sentence, the three-valued discipline.
- Findings as first-class rows with identity across runs — named in `docs/plan.md` Phase 4 and
  still deferred. This is attribution inside the one JSON document, not a new table.

## How to prove it ran

`make verify`, then against `make up`: a real multi-pack run whose report shows each finding
attributed to the correct pack — **with at least two packs that both produce findings**, so a
mis-wired attribution is visible rather than trivially correct. A stored pre-bump document still
renders through the fallback. Rendered browser evidence, and the resolved `source_citation`
reachable from a finding.

## Evidence

### `make verify`

Passed in full (ruff, ruff format, mypy --strict, import-linter's 5 contracts, the
Python suite with `compile-messages`, and the frontend `lint`/`typecheck`/`build`/
`build-workbench`/`test-unit`/`test-storybook`). Full log tail:

```
uv run ruff check .
All checks passed!
uv run ruff format --check .
192 files already formatted
uv run mypy packages/engine/src services/api/cadgpt
Success: no issues found in 174 source files
uv run lint-imports --no-cache
...
I1 - no inference client, web framework or network reaches the checking engine KEPT
The engine knows nothing about the service that hosts it KEPT
Django apps are layered KEPT
Services never import the transport layer KEPT
Models never import services KEPT
Contracts: 5 kept, 0 broken.
cd services/api && uv run --project .. python manage.py compilemessages
processing file django.po in .../locale/fa/LC_MESSAGES
uv run pytest
....................................................... [100%]  (all passed)
...
> @cadgpt/web@0.1.0 build
tsc -b && vite build ... ✓ built in 3.40s
> @cadgpt/web@0.1.0 build-workbench
storybook build ... Storybook build completed successfully
> @cadgpt/web@0.1.0 test-unit
Test Files  1 passed (1)   Tests  2 passed (2)
> @cadgpt/web@0.1.0 test-storybook
Test Files  9 passed (9)   Tests  36 passed (36)
```
Exit code 0 (`make verify > /tmp/verify.log 2>&1; echo "EXIT:$?"` printed `EXIT:0`).

### The real path

`make up`'s `docker compose --build` could not run in this sandbox: the build container
has no route to `pypi.org` (`Connection refused` resolving `hatchling`; the host's own
outbound proxy is loopback-only and unreachable from inside a build container). This is
an environment limitation, not a code issue — logged honestly rather than skipped. The
real path was instead run as the host process against the **same** already-running
Postgres and Redis containers (`docker compose ps` showed them healthy throughout): a
real `manage.py runserver`, a real `celery -A cadgpt.config.celery worker --queues
checks,default`, and the actual frontend (`pnpm run dev`, proxying `/api` to the host
API, per `vite.config.ts`) — no mocks, no stub anywhere in this path.

**Two packs, both producing findings, through the real HTTP API and the real engine.**
Registered a fresh account/tenant/project, uploaded `packages/engine/tests/fixtures/
three_doors.ifc` as the model, requested a check against two of the catalogue's existing
sample packs (`Accessible door width`, `door_width.ids` → FAIL+INDETERMINATE entities;
`Restricted attribute name`, `door_name_restricted.ids` → INDETERMINATE entities — chosen
specifically because neither is a pure PASS, so a mis-wired attribution would be visible).
The run succeeded; its stored `report["specifications"]` from the live API:

```
- 'Minimum clear door width 900 mm' status=FAIL
  rule_pack={'name': 'Accessible door width', 'uuid': '37d6c02b-51c0-4c22-9765-fff56bb41629', 'version': '0.1'}
- 'A recorded overall dimension' status=INDETERMINATE
  rule_pack={'name': 'Restricted attribute name', 'uuid': 'f9764d28-7d91-4826-a289-fba52c2572fb', 'version': '0.1'}
```

`CheckRun.rule_pack_selection` (the same run) resolves each to its `source_citation`:

```
- 37d6c02b-... Accessible door width 0.1 source_citation: cadgpt engine test fixture
  (packages/engine/tests/fixtures/door_width.ids in this repository). ...
- f9764d28-... Restricted attribute name 0.1 source_citation: cadgpt engine test fixture
  (packages/engine/tests/fixtures/door_name_restricted.ids in this repository). ...
```

**Rendered browser evidence** (Playwright/chromium against the real `pnpm run dev` +
real API, signed in through the real login form — screenshot at
`services/web/e2e/screenshots/t0049-two-pack-report.png`, DOM text extracted from the
same page via `getByTestId("spec-source").allTextContents()`):

```
"منبع: Accessible door width — sample v0.1 — cadgpt engine test fixture
(packages/engine/tests/fixtures/door_width.ids in this repository). Not an authored
regulation -- seeded to exercise the rule pack catalogue's storage and selection path
ahead of the product owner's authored packs (docs/plan.md, Phase 3: Iranian building
code first, then EU and US)."

"منبع: Restricted attribute name — sample v0.1 — cadgpt engine test fixture
(packages/engine/tests/fixtures/door_name_restricted.ids in this repository). ..."
```

Each finding is attributed to the correct, distinct pack, and each pack's own
`source_citation` is reached from it — never the same pack for both, never a fabricated
citation.

**The Markdown report (T-0032, already landed) carries it too.** Downloaded the same
run's generated file over the real report-file route:

```
### Minimum clear door width 900 mm — Fail

Source: Accessible door width — sample v0.1

> cadgpt engine test fixture (packages/engine/tests/fixtures/door_width.ids in this
> repository). ...

### A recorded overall dimension — Indeterminate

Source: Restricted attribute name — sample v0.1

> cadgpt engine test fixture (packages/engine/tests/fixtures/door_name_restricted.ids in
> this repository). ...
```

**A stored pre-bump document still renders through the fallback.** This Postgres already
held a `CheckRun` from a prior task's evidence run with `report->>'schema_version' = '4'`
and no `rule_pack` key on any specification at all (queried directly:
`select report->>'schema_version', jsonb_array_length(report->'specifications') from
review_checkrun where uuid='56c06142-7121-4e4c-92d2-2da35440e81c'` → `4`, `1`). Opened
that exact run in the browser (screenshot at
`services/web/e2e/screenshots/t0049-pre-bump-report.png`): it renders fully, with zero
`data-testid="spec-source"` elements and zero console errors on reload — the fallback
this task's Scope requires, keyed off field presence, never off `schema_version`.

### Wiring

- The attribution is applied where several reports become one, and only there —
  `services/api/cadgpt/apps/review/services/execution.py:254`:
  `document = _attribute_specifications(combined, reports, citations)`, and the result is
  what actually gets persisted, `execution.py:344`: `run.report = document` (inside
  `_succeed`, called from `execute` at `execution.py:97`:
  `return self._succeed(run, report, document, log)`). The single-`RuleSet` path
  (`execute`, the `if rule_set is not None:` branch) builds `document = report.to_dict()`
  unchanged — no pack, no attribution, by construction.
- The catalogue's citation carries `source_citation` from the moment it is snapshotted —
  `services/api/cadgpt/apps/rulepack/services.py:235`:
  `"source_citation": rule_pack.source_citation,` inside `RulePackService.snapshot`,
  which `ReviewService._resolve_selection` already calls for every catalogue run.
- The Markdown renderer resolves and prints it — `services/api/cadgpt/apps/review/
  services/report_markdown.py:283`: `lines.extend(_pack_attribution_lines(pack_ref,
  citation_by_uuid))`, reached from inside the per-specification loop of
  `render_markdown_report`, the function `report_generation.py` already calls for every
  succeeded run.
- The screen renders and resolves it — `services/web/src/components/ReportView.tsx:352`:
  `<SpecificationSource pack={spec.rule_pack} selection={rulePackSelection ?? []} />`,
  inside the existing per-specification `<li>` `ReportView` already renders for every
  report.
- `REPORT_SCHEMA_VERSION` bumped 4 → 5 in `packages/engine/src/cadgpt_engine/report.py`,
  documented as the one bump that adds nothing to the engine's own dataclasses (the
  field is layered on downstream, in the service); every reader
  (`presentation.py`'s pass-through, `report_markdown.py`, `ReportView.tsx`,
  `types.ts`'s `rule_pack?:`) degrades on the key's presence, never on comparing the
  version number, matching the T-0027 pattern the task specified.

### Tests added

`test_rule_pack_selection.py::test_every_finding_carries_the_pack_that_produced_it` (two
real packs, real engine, real IFC — asserts distinct attribution and a resolvable
`source_citation`); `test_check_run.py::
test_a_run_against_an_uploaded_rule_set_carries_no_pack_attribution`;
`test_presentation.py`'s two new tests (a v1 document localizes with no `rule_pack`
invented; a `rule_pack` on a specification survives `localize_report` unchanged);
`test_report_markdown.py`'s two new tests (a specification with `rule_pack` renders its
source and citation, one without renders neither). All pass under `make verify` above.

### Fix-now round (reviewer-gated on I5)

The first pass proved the attribution mechanism itself was wired correctly (a live
two-pack run, the Markdown output, the fallback), but a reviewer found two real proof
gaps and two trivial defects, all fixed in this round:

**F1 — neither renderer's pack→citation resolution was tested against a genuinely
multi-pack selection.** The reviewer proved this by mutation: replacing
`report_markdown.py`'s `citation_by_uuid.get(pack_ref["uuid"], {})` with
`next(iter(citation_by_uuid.values()), {})`, and `ReportView.tsx`'s
`selection.find((candidate) => candidate.uuid === pack.uuid)` with `selection[0]`, left
every existing test green, because none of them selected from more than one pack.

Fixed by adding, on both sides, a test with a genuinely two-pack selection where two
specifications are attributed to *different* packs, asserting each specification's own
citation — never the other's, never "whichever pack is first."

- Backend: `services/api/cadgpt/apps/review/tests/test_report_markdown.py::
  test_a_specification_attributed_to_one_pack_never_cites_the_other` — two packs (A, B),
  one specification attributed to each, asserts pack A's section contains only pack A's
  `source_citation` and pack B's section contains only pack B's.
- Frontend: `services/web/src/components/ReportView.stories.tsx`'s `Full` story gained a
  `play` function asserting, via `getByTestId("spec-source")` /
  `getByTestId("spec-source-citation")` scoped to each specification's own `<li class="spec">`,
  that the door-width specification (attributed to `fx.report`'s pack A, "مبحث چهارم")
  shows pack A's name, version and citation, and the spaces specification (attributed to
  pack B, "مبحث سوم") shows pack B's — with an explicit negative assertion that neither
  citation string appears in the other's section.

**Mutation proof, F1 backend** — applied the reviewer's exact mutation, ran the new test,
restored, ran again:

```
$ sed -i 's/citation = citation_by_uuid.get(pack_ref\["uuid"\], {})/citation = next(iter(citation_by_uuid.values()), {})/' report_markdown.py
$ uv run pytest cadgpt/apps/review/tests/test_report_markdown.py -q
...
E       AssertionError: assert 'Citation belonging to pack B only.' in '### A speci...'
FAILED ...test_a_specification_attributed_to_one_pack_never_cites_the_other

$ git checkout -- report_markdown.py   # restored citation_by_uuid.get(...)
$ uv run pytest cadgpt/apps/review/tests/test_report_markdown.py -q
..................... [100%]  (all 19 tests passed)
```

**Mutation proof, F1 frontend** — applied the reviewer's exact mutation to
`SpecificationSource`, ran `pnpm run test-storybook`, restored, ran again:

```
$ # entry = selection.find(candidate => candidate.uuid === pack.uuid)  ->  entry = selection[0]
$ pnpm run test-storybook
 FAIL  |storybook (chromium)| src/components/ReportView.stories.tsx > Full
 Expected element to have text content:
   مقررات ملی ساختمان ایران، مبحث سوم، ویرایش ۱۳۹۵
 Received:
   — مقررات ملی ساختمان ایران، مبحث چهارم، ویرایش ۱۳۹۹
 Test Files  1 failed | 8 passed (9)   Tests  1 failed | 35 passed (36)

$ # restored selection.find(...)
$ pnpm run test-storybook
 Test Files  9 passed (9)   Tests  36 passed (36)
```

**F2 — the frontend attribution render had no test coverage at all.** The reviewer's
mutation (`{false && spec.rule_pack && ...}`) left `test-storybook` at 36/36 unchanged —
the whole feature could be deleted from the UI with nothing noticing.

Fixed as part of the same `Full` story `play` function above: the first block of
assertions (door-width specification) proves the attribution renders at all — pack name,
version and citation text present — distinct from the cross-pack-correctness assertion
that follows it.

**Mutation proof, F2** — commented out `ReportView.tsx`'s render guard
(`{spec.rule_pack && (...)}` → `{false && spec.rule_pack && (...)}`), ran
`pnpm run test-storybook`, restored, ran again:

```
$ pnpm run test-storybook
 FAIL  |storybook (chromium)| src/components/ReportView.stories.tsx > Full
 TestingLibraryElementError: Unable to find an element by: [data-testid="spec-source"]
  ❯ getByTestId src/components/ReportView.stories.tsx:61:38
 Test Files  1 failed | 8 passed (9)   Tests  1 failed | 35 passed (36)

$ # restored {spec.rule_pack && (<SpecificationSource .../>)}
$ pnpm run test-storybook
 Test Files  9 passed (9)   Tests  36 passed (36)
```

**F3 — trivial.** `services/web/src/mocks/fixtures.ts`'s `report` fixture declared
`schema_version: 2` while several of its specifications carry `rule_pack`, a v5-only
field. Bumped to `schema_version: 5`.

**F4 — trivial.** `packages/engine/src/cadgpt_engine/report.py`'s
`REPORT_SCHEMA_VERSION` comment named
`cadgpt.apps.review.services.execution._attribute_specifications` directly inside the
engine package. Reworded to "the service layer that combines several packs' `Report`s
into the one document a run stores" — no module or function named from inside the engine.

F5 (a test for the case where an attributed spec's selection entry doesn't resolve to a
citation) and F6 (the existing two-pack test being one FAIL + one PASS rather than two
packs that both produce findings) were left as the coordinator's recorded observations,
not fixed — both readers already degrade correctly for F5's case, and F6's live-stack
proof already satisfies the task's actual requirement.

### `make verify`, after the fix-now round

Full run, exit 0:

```
uv run ruff check .            -> All checks passed!
uv run ruff format --check .   -> 192 files already formatted
uv run mypy packages/engine/src services/api/cadgpt  -> Success: no issues found in 174 source files
uv run lint-imports --no-cache -> Contracts: 5 kept, 0 broken.
uv run pytest                  -> 306 passed, 35 warnings
pnpm run lint / typecheck / build / build-workbench  -> clean, built
pnpm run test-unit             -> Test Files 1 passed (1)  Tests 2 passed (2)
pnpm run test-storybook        -> Test Files 9 passed (9)  Tests 36 passed (36)
```
(`make verify > /tmp/verify.log 2>&1; echo "EXIT:$?"` printed `EXIT:0`.)

### NOT DONE

Nothing from this fix-now round's F1-F4. Every item landed: a genuinely multi-pack
backend test and its mutation proof (F1 backend), a genuinely multi-pack frontend
Storybook assertion and its mutation proof (F1 frontend), a frontend render-exists
assertion and its mutation proof (F2), the fixture's `schema_version` bump (F3), and the
engine comment reworded to not name the hosting service (F4). F5 and F6 were left
untouched per the coordinator's explicit instruction, recorded above as observations, not
defects.

From the original pass: every item in Scope landed: per-specification pack identity
(uuid/name/version) resolvable to the recorded selection entry, `source_citation`
reachable from a finding on both renderers, the `REPORT_SCHEMA_VERSION` bump with a
field-presence fallback, and the Markdown report carrying it (T-0032 had already
landed). The engine, the counts, the coverage sentence, the three-valued discipline and
findings-as-rows were not touched.

## Review
