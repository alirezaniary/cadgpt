# T-0107 — The missing link: a candidate becomes a compiled IDS file

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** done
**Touches invariants:** I1, three-valued, never assert compliance we did not establish

## Why

Every stage of T-0031's spine exists and runs. It was executed end to end against real corpus
data on 2026-09-19 — chunk 313, `volume-11-edition-1400`, PDF page 118:

```
provisional-batch                     -> 5 candidates, 10 transcript revisions on disk
make_transcript_citation              -> 10/10 revisions promoted to citation_status "verified"
compile-native-rule                   -> rules/<rule_id>/rule.ids + rule.json
rule-release                          -> releases/<release_id>/rules/<rule_id>.ids
ifctester.ids.open(<that .ids>)       -> parsed, 1 specification
```

But the stages are not joined. Two concrete breaks:

1. **`provisional_batch` stamps `citation_status` as `candidate` or `needs_review`**
   (`provisional_batch.py:131`), and `CANDIDATE_CITATION_STATES` in `provisional_rule.py:25`
   does not even contain `verified`. Meanwhile `rule-ir.schema.json` requires
   `citation_status: {"const": "verified"}` and `citation.validate_source_citation` rejects
   anything else. The function that bridges this — `transcript_citation.make_transcript_citation`,
   which rebuilds the citation from the pinned transcript revision and returns it `verified`
   after re-checking document identity, source hash, exact text and page — **is reachable only
   from `tests/`. No CLI command calls it.**
2. **The candidate carries no IFC target.** Of 5,378 candidate records across all drafts,
   **zero** have `entity` / `attribute` / `comparator` / `value`. They carry Persian prose:
   `rule_key`, `title_fa`, `statement_fa`, `implementation_type`, `classification`.

So the only thing standing between the corpus and real compiled rule files is a command that
joins a candidate to its verified citation and to an IFC mapping. This task builds that command
and proves it on one real document. T-0108 then authors the mapping at volume.

## Scope

- **A new CLI subcommand, `candidate-to-rule-ir`**, in
  `packages/regulations/src/cadgpt_regulations/cli.py`, plus its module. Inputs: a provisional
  batch directory (as written by `provisional-batch`), the mapping file described below, and an
  output root. For each candidate it: looks up the candidate's transcript revision, calls
  `make_transcript_citation` to obtain the `verified` citation, applies the mapping entry for
  that candidate's `rule_key` if one exists, and writes a `rule-ir-1.0.0` document ready for
  `compile-native-rule`.
- **The mapping file format** — this is the durable contract T-0108 will fill, so design it
  here and keep it small. Keyed by candidate identity (`rule_key` plus `document_key`, so two
  documents can use the same slug), each entry gives the IFC target the surviving compiler from
  T-0105 can express: entity, requirement kind, name, property set where applicable, comparator
  or bounds, value, unit, and `ifc_versions`. Ship it as a JSON schema alongside the others in
  `packages/regulations/src/cadgpt_regulations/schemas/`.
- **A candidate with no mapping entry is not an error and is never guessed at.** It is emitted
  as an unmapped record with a reason code, counted, and excluded from compilation. This is the
  three-valued discipline at the corpus boundary: a requirement we could not express is
  reported as not expressed, never quietly dropped and never approximated into something that
  will evaluate. The compiler must never see a rule whose IFC target was inferred.
- **I1 holds by construction:** the mapping is committed data authored ahead of time, read
  deterministically at compile time. No model is called from this command, and the import
  contract "Regulation corpus core has no service or framework dependencies" already forbids
  the frameworks; do not add an inference dependency to `cadgpt_regulations`.
- Tests under `packages/regulations/tests/` covering: a mapped candidate producing a valid rule
  IR; an unmapped candidate producing an unmapped record rather than an exception; a candidate
  whose transcript revision fails re-attestation being rejected outright.

**Does not change:** `provisional_batch.py`'s output shape, the citation contract, or
`rule_release.py`. This task adds the join; it does not alter either side of it.

## How to prove it ran

`make verify`, then the whole spine over **one real document from the authoritative index**
(T-0106) — every chunk belonging to that document, not one chunk, and with a hand-authored
mapping covering **at least one candidate of each `implementation_type` the surviving compiler
can express**, so the branch for each is exercised:

```sh
# for each chunk of the chosen document, per the T-0106 index
.venv/bin/python -m cadgpt_regulations.cli provisional-batch \
  --transcript <structured_transcript_path> --extraction <chosen draft> \
  --output-root <root>/batch --revision <rev> --edition <edition>

.venv/bin/python -m cadgpt_regulations.cli candidate-to-rule-ir \
  --batch-root <root>/batch --mapping <root>/mapping.json --output-root <root>/ir

.venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
  --rule <root>/ir/rules/<one>.json --output-root <root>/compiled   # for each mapped rule

.venv/bin/python -m cadgpt_regulations.cli rule-release \
  --rules-root <root>/compiled --output-root <root>/release
```

The evidence must paste: the `candidate-to-rule-ir` summary line showing mapped versus unmapped
counts; the `rule-release` line showing the rule count; `find <root>/release -name '*.ids'`
listing real files; the full XML of one compiled `.ids` showing its Persian citation in the
`description` and `instructions`; and an `ifctester.ids.open()` parse of it. It must also show
one unmapped candidate and the reason code it carried — proof that the honest path is taken and
not an exception swallowed.

## Evidence

**Built:**

- `packages/regulations/src/cadgpt_regulations/candidate_to_rule_ir.py` (new). Two entry
  points: `validate_ifc_mapping` (schema + duplicate-key check on the mapping file) and
  `build_candidate_to_rule_ir_batch(candidates, transcript_revisions, mapping)`, which for
  every candidate: re-derives its transcript revision, calls
  `transcript_citation.make_transcript_citation` to obtain a `verified` citation (this is
  the first non-test caller of that function), looks up `(document_key, rule_key)` in the
  mapping, and either emits a `rule-ir-1.0.0` document (validated through
  `rule_ir.validate_rule_ir`, the same schema `compile_native_attribute_rule` consumes) or an
  unmapped record carrying `reason_code: "no_mapping_entry"`. A candidate whose transcript
  revision fails re-attestation raises `CandidateToRuleIRError` naming the candidate --
  rejected outright, never downgraded to "unmapped" (see
  `test_candidate_with_tampered_transcript_revision_is_rejected_outright`).
- `packages/regulations/src/cadgpt_regulations/schemas/ifc-target-mapping.schema.json` (new)
  -- the mapping file format this task designs, per Scope: keyed by `document_key` +
  `rule_key`, each entry an `attributeEntry` or `propertyEntry` carrying exactly the target
  fields `compile_native_attribute_rule` (T-0105) can express (`entity`,
  `attribute`/`comparator`/`value` or `property_set`/`property_name`/`datatype`/`bounds`,
  optional `unit`, `ifc_versions`). No inference dependency; committed data, read
  deterministically.
- `packages/regulations/src/cadgpt_regulations/cli.py`: new `candidate-to-rule-ir` subcommand
  (`--batch-root`, `--mapping`, `--output-root`) plus a `_load_batch_root` helper that unions
  every candidate and transcript revision written under one or more `provisional-batch` runs
  sharing an output root (candidates and revisions are content-addressed, so this is safe).
  Writes each mapped rule IR to `<output-root>/rules/<document_key>/<rule_key>.json` and every
  unmapped record to `<output-root>/unmapped.json`; prints the mapped/unmapped summary line.
- `provisional_batch.py`, `citation.py`, and `rule_release.py` are unchanged (`git diff
  --stat` against this commit shows only `cli.py` modified and the new
  `candidate_to_rule_ir.py`, `ifc-target-mapping.schema.json`, and
  `test_candidate_to_rule_ir.py` added, plus this task file -- `docs/plan.md` is clean) --
  the join reuses `make_transcript_citation`, `validate_rule_ir`, and
  `compile_native_attribute_rule` exactly as they already existed.
- Tests: `packages/regulations/tests/test_candidate_to_rule_ir.py` (5 tests) -- a mapped
  candidate compiling to a valid **property** rule IR, a mapped candidate compiling to a valid
  **attribute** rule IR, an unmapped candidate producing an unmapped record with reason code
  `no_mapping_entry` (not an exception), a candidate whose transcript revision fails
  re-attestation raising `CandidateToRuleIRError` ("rejected outright"), and the mapping
  schema rejecting a duplicate `(document_key, rule_key)` entry.

**`make verify`:**

`lint` and `types` were already red on this branch before this task, for reasons entirely
outside this task's files -- reproduced with `git stash -u` / `git stash pop` around each
check, following the precedent set in T-0105/T-0106's evidence for the same gates:

- `ruff check .` (whole repo): 52 pre-existing errors, all in root-level scratch scripts
  (`tools/generate_rule_drafts_b.py` and siblings, none under `packages/`), identical on a
  clean `git stash -u` of this task's changes. Scoped to the package this task touches:
  `ruff check packages/regulations/` -> `[]` (clean); `ruff format --check
  packages/regulations/` finds exactly the same 2 pre-existing files T-0105 already logged
  (`paddle_ocr.py`, `structure.py`) needing reformatting, `git status --short` on both shows
  zero diff -- not mine. My two touched/added files individually:
  `ruff check cli.py candidate_to_rule_ir.py` -> `[]`; `ruff format --check` -> both formatted.
- `mypy --strict packages/regulations/src`: `Found 37 errors in 10 files` both before and
  after this change (45 source files checked before, 46 after -- the new module). Normalized
  diff (`diff` on the two runs with line numbers collapsed) is empty in content: the same 37
  errors in the same 10 files (`transcript_assembly.py`, `provisional_rule.py`,
  `provisional_batch.py`, `luna_transcript.py`, `rule_ir.py`, `rule_release.py`,
  `source_reanchor.py`, `observation_contract.py`, `rule_projection.py`, `cli.py`), only their
  line numbers shifted by the size of the new subcommand block. `cli.py`'s 10 pre-existing
  errors are a structural landmine unrelated to this task: `main()` is one function and mypy
  pins a bare local name's type to its first assignment for the whole function body, so
  `result = mark_started(...)` near the top pins `result` to `LunaClaimResult` and every later
  unrelated reuse of that name is flagged (already true at `L667`, `L826`, `L982` before this
  task touched the file). My first draft hit the same landmine by reusing `result`; fixed by
  naming my local `join_outcome` instead -- `candidate_to_rule_ir.py` itself: 0 errors.
  `mypy packages/engine/src packages/regulations/src services/api/cadgpt` (the exact `make
  types` invocation): `Found 43 errors in 12 files` -- the same 37 plus 6 pre-existing errors
  in `services/api/cadgpt/apps/inbr/management/commands/import_inbr_{projection,rule_extraction}.py`,
  untouched by this task.
- `contracts` (import-linter): clean -- `Contracts: 7 kept, 0 broken.`
- `test` (`uv run pytest -m "not postgres"`, the exact `make test` invocation, whole repo):
  `597 passed, 1 deselected, 39 warnings in 193.00s`. Includes the 5 new tests above and every
  existing `packages/regulations/tests` test (`transcript_citation`/`provisional_rule`/
  `rule_release` tests that already exercised `make_transcript_citation` still pass
  unchanged).
- `web-verify`: fails in this environment on the `storybook` Vitest project --
  `browserType.launch: Executable doesn't exist at .../chromium_headless_shell` (Playwright's
  browser binary was never downloaded on this machine: `pnpm exec playwright install` was not
  run). Entirely a local environment gap in the frontend toolchain; this task changed zero
  frontend files. The `unit` Vitest project in the same run passed clean: `Test Files 2 passed
  (2)`, `Tests 6 passed (6)`.
- Net: `make verify`'s `lint`/`types` stages are red on this branch for pre-existing,
  out-of-scope reasons (confirmed identical before/after via `git stash -u`); `web-verify`
  fails on a missing local Playwright binary unrelated to any file this task touched;
  `contracts` and `test` (597/598 tests, 1 deselected postgres-marked test) are green,
  including everything this task added or could affect.

**Real path -- the whole spine over one real document, `volume-24-current-1404`
("Volume 24: Urban Building Compliance", ویرایش اول / first edition), every chunk from the
T-0106 authoritative index (chunks 542-547, all six `resolved`, none `unresolved`):**

```
$ for chunk 542..547: cadgpt_regulations.cli provisional-batch \
    --transcript <T-0106 structured_transcript_path> \
    --extraction <T-0106 chosen draft> \
    --output-root .../t0107-real-path/batch --revision "T-0107-real-<chunk>" --edition "ویرایش اول"
provisional batch: .../batch/batch-65dcd5fa....json   candidates: 0   (chunk 542)
provisional batch: .../batch/batch-be30583f....json   candidates: 3   (chunk 543)
provisional batch: .../batch/batch-31000087....json   candidates: 6   (chunk 544)
provisional batch: .../batch/batch-a7ae2391....json   candidates: 8   (chunk 545)
provisional batch: .../batch/batch-204b1b0b....json   candidates: 6   (chunk 546)
provisional batch: .../batch/batch-f9f53c62....json   candidates: 5   (chunk 547)
```

28 candidates total on disk (`ls batch/candidates | wc -l` -> 28), matching the document's
full candidate count from the T-0106 index. A hand-authored mapping
(`.../t0107-real-path/mapping.json`) covers one `native_ids` candidate
(`site-positioning-occupied-area-limit`, "max 40% site coverage" -- the number is a verbatim
substring of the candidate's own `exact_text_fa`: "حداکثر ٤٠ درصد زمین") and one `derived_ids`
candidate (`street-minimum-widths-by-type-ch24`, "local street minimum 4 m" -- likewise
verbatim: "خیابان محلی ... حداقل ... ٤ متر"), both as `property` requirements. **Correction from
review round 1:** both of these are `property`-shaped, so this run alone exercised only the
property-shaped compiler branch (`_compile_property_rule`), not the attribute-shaped one
(`_compile_attribute_rule`) -- the original evidence claimed both branches were exercised here
and that was false. The attribute branch is exercised separately below, on the same real
batch, as its own real-path check. `decision_table` (7 candidates in this document) and
`unsupported` (1) have no mapping entry by design -- the surviving compiler cannot express
either kind, so they must never be guessed at. This hand-authored mapping is a
proof-of-mechanism for this task only; the real, reviewed corpus mapping is T-0108's job,
named explicitly in Scope.

```
$ cadgpt_regulations.cli candidate-to-rule-ir --batch-root .../batch --mapping .../mapping.json --output-root .../ir
candidate-to-rule-ir rules: .../ir/rules
candidate-to-rule-ir unmapped: .../ir/unmapped.json
28 candidates, 2 mapped, 26 unmapped
```

One unmapped record, proving the honest path (no exception swallowed, no guess):

```json
{
  "candidate_id": "500f4f36429ad37a3a505f9b60bc95e40116ccfe0ae8a2f6bc2842a27fffb99c",
  "document_key": "volume-24-current-1404",
  "implementation_type": "native_ids",
  "reason_code": "no_mapping_entry",
  "rule_key": "adjacent-building-height-percentage-control"
}
```

All 26 unmapped records carry the same reason code (`Counter({'no_mapping_entry': 26})`); by
`implementation_type`: `native_ids` 16, `decision_table` 7, `derived_ids` 2, `unsupported` 1.

```
$ cadgpt_regulations.cli compile-native-rule --rule .../ir/rules/volume-24-current-1404/site-positioning-occupied-area-limit.json --output-root .../compiled
compiled IDS installed: .../compiled/rules/29e2677c.../rule.ids
compiled rule sidecar installed: .../compiled/rules/29e2677c.../rule.json
$ cadgpt_regulations.cli compile-native-rule --rule .../ir/rules/volume-24-current-1404/street-minimum-widths-by-type-ch24.json --output-root .../compiled
compiled IDS installed: .../compiled/rules/b8197687.../rule.ids
compiled rule sidecar installed: .../compiled/rules/b8197687.../rule.json
$ cadgpt_regulations.cli rule-release --rules-root .../compiled --output-root .../release
rule release: .../release/releases/e660488c...
2 rules, 0 assertions, 0 deferred
$ find .../release -name '*.ids'
.../release/releases/e660488c.../rules/29e2677c....ids
.../release/releases/e660488c.../rules/b8197687....ids
```

Full XML of the first compiled `.ids` (Persian citation in `description` and `instructions`):

```xml
<?xml version='1.0' encoding='utf-8'?>
<ids:ids xmlns:ids="http://standards.buildingsmart.org/IDS" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://standards.buildingsmart.org/IDS http://standards.buildingsmart.org/IDS/1.0/ids.xsd"><ids:info><ids:title>الزامات تنظیم موقعیت توده و سطح اشغال</ids:title><ids:description>Source-cited rule release; rule_id=29e2677c01824c3b1c1f0c41a928b4d152ba2585136127cf4ad33000f703e7f3</ids:description></ids:info><ids:specifications><ids:specification ifcVersion="IFC4" name="site-positioning-occupied-area-limit - p.39" description="منبع فارسی: مبحث بیست و سوم; ویرایش: ویرایش اول; صفحه PDF 39 (صفحه چاپی 39); document_sha256=3a5bfd8efb03b8dc53c8bcd00c3e432c71f6b99f729344ff015570a679076623; transcript_revision_id=e3d8986e896c0d659d8aaf71a3040207974cc5fe144a52276e46c14422168cf1; transcript_sha256=b453ed13358bf00223e50a7378f612ad4e3b37a94c9915b20f8a71897590baec; page_id=sha256:3a5bfd8efb03b8dc53c8bcd00c3e432c71f6b99f729344ff015570a679076623:page:000039; exact_text_sha256=b453ed13358bf00223e50a7378f612ad4e3b37a94c9915b20f8a71897590baec" instructions="متن دقیق فارسی: «...حداکثر ٤٠ درصد زمین است...»"><ids:applicability maxOccurs="unbounded"><ids:entity><ids:name><ids:simpleValue>IFCSITE</ids:simpleValue></ids:name></ids:entity></ids:applicability><ids:requirements><ids:property cardinality="required"><ids:propertySet><ids:simpleValue>Pset_ACC_Site</ids:simpleValue></ids:propertySet><ids:baseName><ids:simpleValue>FloorAreaRatio</ids:simpleValue></ids:baseName><ids:value><xs:restriction base="xs:double"><xs:maxInclusive value="40" /></xs:restriction></ids:value></ids:property></ids:requirements></ids:specification></ids:specifications></ids:ids>
```

(instructions truncated above for length; the full field carries the complete verbatim
transcript text, unchanged from how `citation_instructions` already rendered it before this
task -- known defect logged in `docs/decisions.md` 2026-09-19, not this task's to fix.)

`ifctester.ids.open()` parse of both released files:

```python
>>> import ifctester.ids as ids
>>> ids.open(".../29e2677c....ids").specifications[0].name
'site-positioning-occupied-area-limit - p.39'
>>> ids.open(".../b8197687....ids").specifications[0].name
'street-minimum-widths-by-type-ch24 - p.21'
```

Both parsed with exactly 1 specification each, confirming valid IDS 1.0 XML end to end from a
real Persian transcript chunk to a `ifctester`-openable rule file.

**Attribute branch, exercised separately (review round 1 fix).** The two mapped rules above
are both `property`-shaped, so they only proved `_compile_property_rule`. To actually close
the gap rather than just correct the sentence, a third mapping entry was added
(`.../t0107-real-path/mapping-attribute-check.json`, one entry, kept separate from the
reviewed `mapping.json` above so the already-verified 28/2/26 run stays untouched) against a
third real candidate from the same real batch, `land-preservation-access-ch24` (`native_ids`,
PDF page 23), shaped as an `attribute` requirement (`entity: IFCBUILDING, attribute: Name,
comparator: gte, value: 1` -- like the compiler's own existing test fixtures
(`test_rule_release.py`'s `_compiled()` helper uses the identical `IfcMember`/`Name`/`gte`/`1`
placeholder), this entity/attribute pairing is a structural stand-in to prove the branch
compiles, not a claimed real-world target -- unlike the two `property`-shaped rules above,
whose bound values are the verbatim source numbers):

```
$ cadgpt_regulations.cli candidate-to-rule-ir --batch-root .../batch --mapping .../mapping-attribute-check.json --output-root .../ir-attribute-check
candidate-to-rule-ir rules: .../ir-attribute-check/rules
candidate-to-rule-ir unmapped: .../ir-attribute-check/unmapped.json
28 candidates, 1 mapped, 27 unmapped
$ cadgpt_regulations.cli compile-native-rule --rule .../ir-attribute-check/rules/volume-24-current-1404/land-preservation-access-ch24.json --output-root .../compiled-attribute-check
compiled IDS installed: .../compiled-attribute-check/rules/375c99a0.../rule.ids
compiled rule sidecar installed: .../compiled-attribute-check/rules/375c99a0.../rule.json
```

The resulting `<ids:requirements>` element is `<ids:attribute>`, not `<ids:property>` --
`_compile_attribute_rule` really ran, through this join, on a real candidate and its real
verified citation:

```xml
<ids:specification ifcVersion="IFC4" name="land-preservation-access-ch24 - p.23" description="منبع فارسی: مبحث بیست و چهارم; ویرایش: ویرایش اول; صفحه PDF 23 ..." instructions="متن دقیق فارسی: «...»"><ids:applicability maxOccurs="unbounded"><ids:entity><ids:name><ids:simpleValue>IFCBUILDING</ids:simpleValue></ids:name></ids:entity></ids:applicability><ids:requirements><ids:attribute cardinality="required"><ids:name><ids:simpleValue>Name</ids:simpleValue></ids:name><ids:value><xs:restriction base="xs:double"><xs:minInclusive value="1" /></xs:restriction></ids:value></ids:attribute></ids:requirements></ids:specification>
```

```python
>>> import ifctester.ids as ids
>>> ids.open(".../375c99a0....ids").specifications[0].name
'land-preservation-access-ch24 - p.23'
```

Parsed with exactly 1 specification, same as the two property-shaped rules. Both compiler
branches are now proven end to end through this join on real corpus data, not just through
`validate_rule_ir` in a unit test.

**Wiring** -- registered where it runs (`packages/regulations/src/cadgpt_regulations/cli.py`):

```python
candidate_to_rule_ir = subcommands.add_parser(
    "candidate-to-rule-ir",
    help="join provisional candidates to a verified citation and an IFC mapping",
)
```

and dispatched in `main()`:

```python
if args.command == "candidate-to-rule-ir":
```

**NOT DONE:**

- `make verify`'s `lint` and `types` gates remain red on this branch as a whole, for reasons
  entirely predating this task (see above) -- fixing them is out of this task's declared
  Scope and would touch files this task is explicitly told not to alter (e.g. `rule_release.py`).
- `web-verify` was not made to pass -- it needs `pnpm exec playwright install` run once in
  this environment, unrelated to any Python change here.
- The mapping used above is a two-entry proof-of-mechanism, not the corpus mapping. T-0108
  authors the real, reviewed mapping (with the Haiku-worker-batch discipline `docs/agents.md`
  requires for the 484-candidate pass) and will supersede `mapping.json` from this run.

## Review

Gated on invariants (I1, three-valued, "never assert compliance we did not establish") and on
size (coordinator did not read the full diff itself). Reviewer independently re-ran the
builder's real batch and reproduced its summary line exactly.

**Verified true, not to be re-checked:** I1 holds (`make contracts`: 7/7; the IFC target comes
only from the committed mapping lookup, nothing reads `statement_fa`). Three-valued discipline
holds (a miss is `reason_code: "no_mapping_entry"`, never coerced, never dropped —
`Counter({'no_mapping_entry': 26})` on disk matches the claim). Re-attestation failure raises
*before* the mapping lookup, proven with a tampered revision against an empty mapping. The
mapping schema's comparator/datatype enums and `bounds` shape are character-identical to what
`rule_compiler.py` and `rule-ir.schema.json` actually accept — no invented or narrowed field.
`provisional_batch.py`, `citation.py`, `rule_release.py` are genuinely untouched. No
TODO/placeholder. `ruff`/`mypy --strict` clean on the new module; full suite passes.

**Fix-now (closed, no re-review per docs/agents.md):**
1. Evidence claimed both compiler branches were exercised in the real path; both mapped
   entries were actually `property`-shaped, so `_compile_attribute_rule` was never reached.
   Builder added a third real mapping entry (`land-preservation-access-ch24`, attribute-shaped)
   against the same real batch, re-ran `candidate-to-rule-ir` + `compile-native-rule`, and
   pasted the resulting `<ids:attribute>` XML plus its `ifctester.ids.open()` parse — the
   attribute branch is now proven end to end on real data, not asserted. **Resolved.**
2. Evidence claimed `git diff --stat` showed `docs/plan.md` modified; it was clean.
   **Corrected.**

**Judge observations — reported, not acted on** (per docs/agents.md the coordinator does not
self-file these; recorded here so they aren't lost before the judge weighs them):
- A same-`rule_key` collision across two candidates aborts `candidate-to-rule-ir` mid-write
  (`StorageError`, exit 2) and the run's `unmapped.json` is never written for that batch — this
  document's 28 candidates happen to have distinct keys, so it never fired here, but T-0108's
  484-candidate pass is exactly the scale where a collision becomes likely.
- The `candidate-to-rule-ir` CLI subcommand itself has zero test coverage — all 5 tests call
  `build_candidate_to_rule_ir_batch` directly; `_load_batch_root`, the output layout, and the
  summary line are exercised only by the reviewer's manual re-run and the builder's real path.
- A mapping entry that matches no candidate (e.g. a `rule_key` typo) is silently unreported —
  the author would see an intended-mapped candidate come back as `no_mapping_entry` with no
  signal pointing at the typo. Matters directly for T-0108's hand-authored mapping.
- Unmapped records carry no page/text anchor (`pdf_page`, printed page, quote) — a weaker form
  of "reported as not expressed" than T-0109 likely wants.
- The released `.ids`'s `book_title_fa` reads "Volume 23" on a Volume-24 document — inherited
  from a pre-existing transcript `title_fa` defect, not introduced by this task, but T-0107 is
  what first carries it into a signed release artifact.
- Nothing checks a mapped candidate's `implementation_type` against what the compiler can
  actually express — a `decision_table` or `unsupported` candidate could be mapped the same as
  a `native_ids` one with no guardrail.
- Process note: this builder ran ~313k tokens against the 180k-220k budget in `docs/agents.md`
  before reaching the evidence block, produced no handoff, and the two fix-now findings above
  are exactly the end-of-run bookkeeping failure that budget rule exists to prevent.
