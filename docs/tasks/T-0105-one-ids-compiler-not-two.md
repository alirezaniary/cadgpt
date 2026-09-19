# T-0105 — One IDS compiler, not two: retire the unwired duplicate

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** built
**Touches invariants:** I1, import contracts

## Why

`packages/regulations/src/cadgpt_regulations/` contains two independent implementations of the
same job, each with its own `CompiledRule` dataclass, its own citation validation, and its own
IDS XML emitter:

- `rule_compiler.py` (199 lines) — `compile_native_attribute_rule`. Builds XML with
  `xml.etree.ElementTree`. Supports `attribute` requirements only, scalar comparators only
  (`eq`/`equals`/`gt`/`gte`/`lt`/`lte`). **This is the one wired into the CLI**
  (`cli.py:58`, `cli.py:811`, subcommand `compile-native-rule`), the one `rule_release.py`'s
  tests use, and the one `packages/engine/tests/test_check.py:430,488` imports.
- `ids_compiler.py` (298 lines) — `compile_native_rule`. Builds XML by string assembly.
  Supports `attribute` **and** `property` requirements, `bounds` objects with multiple facets,
  enumerations, and four datatypes (`double`/`decimal`/`integer`/`string`). **Referenced by
  nothing outside `tests/test_ids_compiler.py`.**

So the richer compiler is dead code and the shipped compiler is the narrower one. Every task
after this one builds on whichever survives, and T-0108's mapping vocabulary is decided by the
answer — `ids_compiler` can express a `property` in a property set, which is how most IFC
quantities actually live, and `rule_compiler` cannot. Leaving both in place means the next
builder picks one by accident.

Verified 2026-09-19: `compile-native-rule` was run against a rule IR built from a real
chunk-313 transcript citation and produced a valid `.ids` that `ifctester.ids.open()` parsed.
`ids_compiler.compile_native_rule` has never been run on anything but its own test fixtures.

## Scope

Decide which compiler survives and delete the other, along with its tests. The recommendation,
which the builder should follow unless it finds a concrete reason not to and says so in the
evidence: **keep `ids_compiler.py`'s capability, keep `rule_compiler.py`'s wiring.** That means
porting `ids_compiler`'s `property` / `bounds` / datatype support into the surviving module
rather than deleting it outright — a rule that needs `Pset_SpaceCommon.NetFloorArea` is not
expressible today and T-0108 will need it.

- `packages/regulations/src/cadgpt_regulations/rule_compiler.py` and `ids_compiler.py` — one
  module after this task, not two. `CompiledRule` is defined once.
- `packages/regulations/src/cadgpt_regulations/schemas/rule-ir.schema.json` — if `property`
  requirements survive, the schema must express them. Today it requires a flat `attribute`
  string and forbids extra keys (`additionalProperties: false`).
- `packages/regulations/src/cadgpt_regulations/cli.py` — `compile-native-rule` keeps its name
  and its arguments; only the import moves.
- `packages/regulations/src/cadgpt_regulations/__init__.py` — remove the retired export.
- `packages/regulations/tests/test_rule_compiler.py`, `test_ids_compiler.py` — merge into one
  suite covering both requirement kinds.
- `packages/engine/tests/test_check.py:430,488` — update the import.

**Does not change:** the citation contract (`citation.py`, `source_citation.py`,
`transcript_citation.py`), `rule_release.py`, or the IDS output for a rule that both compilers
could already express — an existing `attribute`+`gte` rule must still compile byte-identically,
because `rule_id` is a hash of the canonical rule and changing it silently invalidates every
artifact hash downstream. If byte-identity cannot be preserved, say so explicitly in the
evidence rather than quietly changing hashes.

## How to prove it ran

`make verify`, then the real path twice over — once for each requirement kind, from real corpus
data, not a fixture:

```sh
# 1. attribute rule, byte-identity with the pre-change compiler
.venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
  --rule <a rule IR built from a real chunk-313 transcript citation> \
  --output-root <private tmp root>
sha256sum <output-root>/rules/*/rule.ids

# 2. property rule — impossible before this task
.venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
  --rule <the same citation, requirement kind "property", a real property set> \
  --output-root <private tmp root>
.venv/bin/python -c "from ifctester import ids; d=ids.open('<the .ids>'); print(len(d.specifications), d.specifications[0].name)"
```

The evidence must show: the attribute `.ids` SHA-256 before and after the change (equal, or an
explicit statement of why not); the property `.ids` parsing under `ifctester`; and
`grep -rn "ids_compiler\|rule_compiler" packages/ services/` returning only the surviving name.

## Evidence

**Resolution taken:** the recommended one. `rule_compiler.py` survives with its CLI wiring
unchanged (`compile_native_attribute_rule`, subcommand `compile-native-rule`, same name, same
arguments). `ids_compiler.py`'s property/bounds/datatype capability was ported into
`rule_compiler.py` as a second internal path (`_compile_property_rule`), dispatched by a new
`requirement_kind` field (`"attribute"`, the default, or `"property"`) on the same public
function, so every existing call site (`cli.py`, `rule_release.py`'s tests, `rule_projection.py`'s
tests, `packages/engine/tests/test_check.py:430,488`) needed no change — they already imported
`compile_native_attribute_rule` from `rule_compiler`, which is why `test_check.py`'s import lines
are identical before and after. `ids_compiler.py` and `tests/test_ids_compiler.py` are deleted;
their coverage is merged into `tests/test_rule_compiler.py` (7 new tests: property compile with
bounds, determinism, unsupported datatype, missing bounds, multi-facet bounds, shared-citation
rejection) and `tests/test_rule_ir.py` (3 new tests: property acceptance, wrong-type bound,
non-integer bound for `datatype: integer`). `rule-ir.schema.json` is now a `oneOf` of
`attributeRule` (byte-identical to the old schema) and a new `propertyRule` branch requiring
`requirement_kind`, `property_set`, `property_name`, `datatype`, `bounds`; `rule_ir.py`'s semantic
validation branches on `requirement_kind` to check bounds-facet values against the declared
datatype (numeric and finite, or integral for `datatype: integer`; non-empty string otherwise).
`CompiledRule`, the sidecar shape (`schema_version`, `rule_id`, `compiler_version`, `ids_sha256`,
`canonical_rule`, `source_citation`, `source_citation_sha256`, `source_attestation` for transcript
evidence) and the citation contract (`citation.py`) are identical for both requirement kinds and
unchanged from before this task — `rule_release.py` and `rule_projection.py` needed no edits.
`packages/regulations/src/cadgpt_regulations/__init__.py` is unchanged: checked (`grep -n
"rule_compiler\|ids_compiler\|CompiledRule\|compile_native" __init__.py` → no match) and neither
module was ever exported from it, so there was no retired export to remove.

**`make verify`:** `contracts` (import-linter) passes clean: `Contracts: 7 kept, 0 broken.` `test`
passes clean for every test this task touches or could affect:
`.venv/bin/python -m pytest packages/regulations/tests/ --color=no` → `256 passed in 95.53s`;
`.venv/bin/python -m pytest packages/engine/tests/ --color=no` → `135 passed, 1 warning in 2.31s`
(the one warning is a pre-existing benign `PytestUnraisableExceptionWarning` from
`ifcopenshell.file.__del__`'s teardown, unrelated to this change, present identically before and
after). `lint` (`ruff check .` / `ruff format --check .`, whole repo) and
`types` (`mypy --strict` over `packages/regulations/src`) both fail on this branch, but **not
because of this change** — verified by `git stash`/`git stash pop` around each check:

- `ruff check .` on the clean pre-change tree already reports 52 errors, all in
  `build_chunk301.py` (a committed root-level scratch script, commit `fd4b6ea`) and other files
  outside `packages/`. `ruff format --check .` on the clean pre-change tree already reports 7
  files needing reformatting, none of them touched by this task (e.g.
  `tools/paddleocr/run_safe.py`). Every file this task changed passes both individually:
  `ruff check <changed files>` → `All checks passed!`; `ruff format --check <changed files>` →
  `6 files already formatted`. Scoped to the package this task touches,
  `ruff format --check packages/regulations/` finds exactly 2 files needing reformatting —
  `paddle_ocr.py` and `structure.py` — and `git status --short` on both confirms zero diff: pre-
  existing, not mine.
- `mypy --strict packages/regulations/src` reports "Found 37 errors in 10 files" both before and
  after this change (46 source files checked before, 45 after — `ids_compiler.py` deleted). The
  errors are the same 37: `rule_ir.py` has 2 (`Redundant cast to "dict[str, Any]"`, at the two
  `cast(JsonObject, ...)` calls that were already present, unmodified, in the pre-existing code —
  only their line numbers shifted because of an added docstring), and the other 35 are in
  `luna_transcript.py`, `transcript_assembly.py`, `rule_release.py`, `observation_contract.py`,
  `rule_projection.py`, `source_reanchor.py`, `provisional_rule.py`, `provisional_batch.py` and
  `cli.py` — none of them files this task's scope touches for behaviour (only `provisional_rule.py`
  got a one-line docstring cross-reference fix, at a line untouched by mypy's complaints there).
  Diffing the two mypy runs (`diff mypy-pre.txt mypy-post.txt`, line numbers normalised) shows the
  only difference is the "N source files" count in the summary line.
- **NOT DONE (out of this task's scope):** `make verify`'s `lint` and `types` gates were already
  red on this branch before T-0105 started, for reasons entirely outside `packages/regulations`
  (a stray root-level script, unrelated formatting drift, and pre-existing type errors across
  eight other regulations modules this task does not touch). Fixing those is a separate task; this
  evidence shows this change adds zero new lint or type errors and the file set this task owns is
  clean under both gates.

**Real path — run twice, from real corpus data, not a fixture.** Citation built from
`.cadgpt/inbr/worker-drafts/luna-1/chunk-313-response.json` (`document_sha256`
`07283f909f9e7c3f9189f6518a1ec9f3215025c78d72727e19528282794ad477`, `pdf_page` 118, the verbatim
OCR `text_fa` for that page) cross-referenced against
`packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json`'s real catalog entry for
`volume-11-edition-1400` (title, edition) — a real chunk-313 transcript citation, per the task's
instruction (worker-drafts contents were only read, never modified).

*1. Attribute rule — byte-identity with the pre-change compiler.* Compiled the same rule IR once
with the pre-change `rule_compiler.py` (git-stashed working tree) and once with the post-change
one:

```
$ .venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
    --rule /tmp/t0105-proof/attr_rule.json --output-root /tmp/t0105-proof/pre-output
compiled IDS installed: /tmp/t0105-proof/pre-output/rules/0229590aac72c9cd637b47901d0964ca9dd95fffcd49448a0a861cf3ceedfa55/rule.ids
compiled rule sidecar installed: /tmp/t0105-proof/pre-output/rules/0229590aac72c9cd637b47901d0964ca9dd95fffcd49448a0a861cf3ceedfa55/rule.json

$ .venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
    --rule /tmp/t0105-proof/attr_rule.json --output-root /tmp/t0105-proof/post-output
compiled IDS installed: /tmp/t0105-proof/post-output/rules/0229590aac72c9cd637b47901d0964ca9dd95fffcd49448a0a861cf3ceedfa55/rule.ids
compiled rule sidecar installed: /tmp/t0105-proof/post-output/rules/0229590aac72c9cd637b47901d0964ca9dd95fffcd49448a0a861cf3ceedfa55/rule.json

$ sha256sum /tmp/t0105-proof/pre-output/rules/*/rule.ids /tmp/t0105-proof/post-output/rules/*/rule.ids
6ddcb776c07eb879228dcc83450c0e534465f44283a1a0a77db82a760ddb6215  pre-output/rules/.../rule.ids
6ddcb776c07eb879228dcc83450c0e534465f44283a1a0a77db82a760ddb6215  post-output/rules/.../rule.ids

$ diff pre-output/rules/*/rule.ids post-output/rules/*/rule.ids && echo IDENTICAL
IDENTICAL
```

Equal SHA-256 before and after: `rule_id` and every downstream artifact hash for this rule shape
are unchanged.

*2. Property rule — impossible before this task.* Same citation, `requirement_kind: "property"`,
`property_set: "Pset_SpaceCommon"`, `property_name: "NetFloorArea"`, `datatype: "double"`,
`bounds: {"minInclusive": 9.0}`:

```
$ .venv/bin/python -m cadgpt_regulations.cli compile-native-rule \
    --rule /tmp/t0105-proof/property_rule.json --output-root /tmp/t0105-proof/property-output
compiled IDS installed: /tmp/t0105-proof/property-output/rules/985647f330a5b36775d5a84df952074b53caf712d9ba027d7148b23a743f5d31/rule.ids
compiled rule sidecar installed: /tmp/t0105-proof/property-output/rules/985647f330a5b36775d5a84df952074b53caf712d9ba027d7148b23a743f5d31/rule.json

$ .venv/bin/python -c "
from ifctester import ids
d = ids.open('/tmp/t0105-proof/property-output/rules/985647f330a5b36775d5a84df952074b53caf712d9ba027d7148b23a743f5d31/rule.ids')
print(len(d.specifications), d.specifications[0].name)
print('requirements:', [type(r).__name__ for r in d.specifications[0].requirements])
"
1 industrialized-space-minimum-net-floor-area - p.118
requirements: ['Property']
```

`ifctester` parses the compiled `.ids` and resolves the requirement to its own `Property` facet
class — this shape did not exist in the wired compiler before this task; before T-0105 it only
existed, unwired, in `ids_compiler.py`, reachable from nothing but its own tests.

**`grep -rn "ids_compiler\|rule_compiler" packages/ services/`** — only the surviving name, no
live `ids_compiler` reference remains (two prose mentions of the historical retirement in
`rule_compiler.py`'s module docstring and a test docstring were reworded to avoid the string
entirely so the grep is unambiguous):

```
packages/engine/tests/test_check.py:430:    from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
packages/engine/tests/test_check.py:488:    from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
packages/regulations/src/cadgpt_regulations/provisional_rule.py:3:Provisional artifacts are intentionally separate from :mod:`rule_compiler`: they
packages/regulations/src/cadgpt_regulations/cli.py:58:from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
packages/regulations/tests/test_rule_release.py:12:from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
packages/regulations/tests/test_rule_compiler.py:12:from cadgpt_regulations.rule_compiler import RuleCompileError, compile_native_attribute_rule
packages/regulations/tests/test_rule_projection.py:10:from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
```

**Wiring** — `compile-native-rule` is still the same subcommand, same import, same call site,
quoted verbatim from `packages/regulations/src/cadgpt_regulations/cli.py`:

```python
# line 58
from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
# lines 299-304
compile_native = subcommands.add_parser(
    "compile-native-rule",
    help="compile one citation-bearing native IDS rule from canonical rule IR",
)
compile_native.add_argument("--rule", type=Path, required=True)
compile_native.add_argument("--output-root", type=Path, required=True)
compile_native.add_argument("--compiler-version", default="native-ids-1.0.0")
# lines 809-813
if args.command == "compile-native-rule":
    rule = load_object(args.rule, description="canonical rule")
    compiled = compile_native_attribute_rule(
        rule, compiler_version=args.compiler_version
    )
```

**NOT DONE:** nothing within this task's scope. Out of scope and explicitly flagged above: the
`lint` and `types` gates of `make verify` were already broken on this branch before T-0105, for
reasons in files this task does not own; that pre-existing debt is unfixed and is not this task's
to fix.

### Review fix-now: H1, H2

Review found two consumers of the rule IR that this task widened without updating, both fixed in
place (property rules are in scope for both — no typed "not supported yet" error needed):

**H1 — `rule_relations.py:68` `_semantic_identity`** unconditionally read `rule["attribute"]`,
`rule["comparator"]`, `rule["value"]`, which a property-kind rule (`requirement_kind: "property"`)
never has — `validate_rule_ir` no longer guarantees those keys, so this was a bare `KeyError` on
any property rule reaching `build_occurrence_assertions`, in shipped code. Fixed by branching on
`requirement_kind`: the attribute branch is untouched (identical dict, identical hashing, so
existing assertion IDs do not move — the same "does not change" concern as the compiler's byte
identity, now honoured here too); a new property branch builds identity from
`entity`/`property_set`/`property_name`/`datatype`/`bounds`/`unit`/`ifc_versions` instead.

**H2 — `rule_capability.py:76` `classify_rule`/`_unsupported_reason`** hardcoded the attribute-only
comparator set, so every property rule — which carries no `comparator` key at all — fell through
to `reason_code: "UNSUPPORTED_COMPARATOR"` and was deferred, even though the compiler has natively
supported the shape since this task's first pass. T-0108 was told to reuse `classify_rule` as-is
for exactly this shape, so leaving it broken would have pushed the fix into that task. Fixed by
short-circuiting `_unsupported_reason` to `None` for `requirement_kind: "property"` before the
comparator check runs; shape validity (bad `datatype`, bounds/datatype mismatch) is still caught
by the existing `validate_rule_ir` call immediately below, which raises `RuleIRError` and is mapped
to `reason_code: "RULE_IR_INVALID"` — no new deferral path needed.

**Tests added:** `test_rule_relations.py` — `test_groups_duplicate_property_rule_occurrences_without_crashing`,
`test_keeps_distinct_property_bounds_as_distinct_assertions`,
`test_attribute_and_property_rules_never_collide`. `test_rule_capability.py` —
`test_classifies_property_bounds_rule_as_supported`, `test_still_defers_malformed_property_rule`.
Full regulations suite: `.venv/bin/python -m pytest packages/regulations/tests/ --color=no` →
`261 passed in 100.26s` (256 + 5 new). `ruff check`/`ruff format --check` on both changed files
and their tests: clean. `mypy --strict packages/regulations/src`: still exactly the same
pre-existing 37 errors (verified by re-running and diffing against the earlier capture) — zero new
errors from either fix, and neither `rule_relations.py` nor `rule_capability.py` appears in the
error list before or after.

**Real path, re-run through both fixed functions on the same property rule used for the compiler's
real-path proof (`/tmp/t0105-proof/property_rule.json`, built from the real chunk-313 citation):**

```
$ .venv/bin/python -c "
import json
from cadgpt_regulations.rule_relations import build_occurrence_assertions
from cadgpt_regulations.rule_capability import classify_rule

rule = json.load(open('/tmp/t0105-proof/property_rule.json'))

relations = build_occurrence_assertions([rule, rule])
print('H1 build_occurrence_assertions summary:', relations['summary'])
print('H1 assertion semantic:', json.dumps(relations['assertions'][0]['semantic'], ensure_ascii=False))

result = classify_rule(rule)
print('H2 classify_rule status:', result['status'])
print('H2 classify_rule rule_id:', result.get('rule_id'))
"
H1 build_occurrence_assertions summary: {'input_occurrences': 2, 'assertions': 1, 'duplicates_collapsed': 1}
H1 assertion semantic: {"requirement_kind": "property", "entity": "IFCSPACE", "property_set": "Pset_SpaceCommon", "property_name": "NetFloorArea", "datatype": "double", "bounds": {"minInclusive": 9.0}, "unit": "m2", "ifc_versions": ["IFC4"]}
H2 classify_rule status: native_supported
H2 classify_rule rule_id: c4349f60d37e538168d9ae9ac4b91252c9b2c24a25f1d873d08ae6b90035496d
```

No crash (H1: two occurrences of the same property rule correctly collapse to one assertion,
proving the identity dict hashes rather than raising), and the property rule classifies as
`native_supported` (H2), not `deferred`/`UNSUPPORTED_COMPARATOR`.

Not addressed, per the coordinator's explicit "leave these alone": H3, M1, M2, M3, L1.

## Review
