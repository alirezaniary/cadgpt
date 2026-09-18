# T-0105 — One IDS compiler, not two: retire the unwired duplicate

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
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

<!-- the builder writes this -->

## Review
