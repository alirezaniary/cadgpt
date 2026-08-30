# T-0009 — The property vocabulary is inherited, and what we author is the residue

Slice: S1.1.1 · Capability: C1.1 · Outcome: O1

## Prerequisites
| Requires | Evidence |
| --- | --- |
| P0 | `make verify` exits 0, "9 gates registered, 0 failed" |

## Objective
`docs/roadmap/L3-C11-slices.md` S1.1.1. Before a single property name is written as code,
every name in `prd.md` §5.3 resolves to **either** an existing IFC property/quantity definition,
adopted by its exact IFC name, **or** a recorded statement that we authored it here and what
nothing existing covers.

This is DEC-0019 and I3 — inherit before authoring — applied at the one moment it is cheap.
If this task authors more names than §5.3 lists, I3 was violated.

The output is **committed data: one table in one document.** No code, no module, no `src/`.

## Context — read these and nothing else
- `CLAUDE.md`
- `prd.md` §5.3 ("The model") — the vocabulary block is the input to this task
- `docs/ddd/02-ubiquitous-language.md`
- `decisions/DEC-0019-inherited-vs-authored-in-the-rule-layer.md`
- `docs/roadmap/L3-C11-slices.md`
- `docs/ddd/README.ai.md`

## Method — established by the Lead, do not redesign
IFC's own property and quantity templates ship **offline** inside `ifcopenshell`, which is
already in the `engine` dependency group. Query them:

```
uv run --group engine python -c "
from ifcopenshell.util.pset import PsetQto
q = PsetQto('IFC4')
t = q.get_by_name('Qto_SpaceBaseQuantities')
print([p.Name for p in t.HasPropertyTemplates])"
```

which prints, among others, `GrossFloorArea`, `NetFloorArea`, `Height`, `GrossPerimeter`.

**The Lead has already run this, and the answer shapes the task.** IFC ships the *quantity
kinds* and ships them as **bare names with no measurement convention** — `NetFloorArea`, not
`NetFloorArea_InsideFace`. That is exactly the gap `prd.md` §5.3 exists to close. So the
expected result is not "adopt everything" or "author everything", but a split down the middle
of each name:

- the **base quantity** is inherited, and our name must use IFC's spelling of it exactly;
- the **convention suffix** is authored here, because IFC has no concept of one.

A row that adopts a base name while silently respelling it (`FloorArea` for IFC's
`NetFloorArea`) is the failure this task exists to prevent, and it is worse than authoring,
because it looks inherited.

**Network:** bSDD (`api.bsdd.buildingsmart.org`) is reachable and its `TextSearch/v2` endpoint
works *without* a `DictionaryUris` filter — with one, the Lead's queries returned zero hits even
for `IfcWall`, so a zero from a filtered query means the query is wrong, not that the term is
absent. You may consult bSDD **by hand** to corroborate a row. Nothing you commit may query it:
gate 16 forbids a test that reaches the network, and this task commits no code at all.

## Contract
Create `docs/ddd/06-property-vocabulary.md`, containing one table with exactly one row per
property name in `prd.md` §5.3, and these columns:

| Column | Content |
| --- | --- |
| `Name` | the §5.3 name, verbatim |
| `Pset` | the §5.3 pset it sits in, verbatim |
| `Base quantity` | the IFC property/quantity template name it inherits, or `—` |
| `Inherited from` | the IFC pset/qto template the base came from, or `authored` |
| `Convention` | the convention segment of our name, or `—` if it carries none |
| `Why authored` | for any row with no base quantity: what nothing existing covers. One sentence. Empty for inherited rows. |

Plus, in prose:

1. **The counts.** How many of §5.3's names inherit a base quantity, how many are authored
   whole, and how many convention segments are authored. State them; do not make the reader add
   the table up.
2. **Any name in §5.3 that should be respelled to match IFC.** If §5.3 says `PlanArea_Net` and
   IFC's quantity is `NetArea`, say so plainly. Do **not** edit `prd.md` — it is the product
   source of truth and changing it is a decision request, not a task. List the proposed
   respellings and stop there.
3. **Every name that carries no convention segment.** `FloorAreaRatio`, `RiserCount`,
   `StallCount` are ratios and counts, not measurements under a convention. Say which names are
   legitimately convention-free and why, because the next slice enforces "every quantity names
   its convention" at construction and needs to know what the exceptions are.

## Invariants this task must uphold
- **I4.** No jurisdiction, country, code body or clause reference in any name, anywhere in the
  document. Gate 5 does not scan Markdown, so this one is on you.
- **No invention.** A base quantity is inherited only if it really exists in the IFC templates
  and you ran the query that shows it. A row asserting an inheritance that is not there is the
  worst output this task can produce — it makes an authored name look ratified.
- **"Not found" names the query.** If a name has no IFC counterpart, the row says `authored` and
  the prose says what you searched. Never a silent `—`.
- **`prd.md` is not edited.** Proposed respellings are listed, not applied.

## Files
Create: `docs/ddd/06-property-vocabulary.md`
Modify: `docs/ddd/README.ai.md` (add the new document to its index)
Forbidden: everything else. In particular `prd.md`, and anything under `src/` or `tools/` —
this task writes no code and creates no module.

## Tests
None. This task commits no code. Its check is the acceptance command below and the honesty of
its rows.

## Acceptance
```
# every §5.3 name appears exactly once in the table, and no name is invented
uv run --group dev python - <<'PY'
import re, pathlib
prd = pathlib.Path("prd.md").read_text()
block = prd.split("Pset_ACC_Site")[1].split("```")[0]
names = set(re.findall(r"[A-Z][A-Za-z]+(?:_[A-Za-z/]+)?", block)) - {"Pset_ACC_Stair","Pset_ACC_Space","Pset_ACC_Shaft","Pset_ACC_Parking","Pset_ACC_Route"}
doc = pathlib.Path("docs/ddd/06-property-vocabulary.md").read_text()
missing = sorted(n for n in names if n not in doc)
print("missing rows:", missing or "none")
raise SystemExit(1 if missing else 0)
PY

make verify        # exits 0, 9 gates, 0 failed — unchanged by this task
```
The first command is a starting point, not a specification: `prd.md` §5.3 writes
`Setback_North/South/East/West` as one line meaning four names. Read the block yourself, say in
your report how many names you found, and adjust the extraction if it miscounts — then quote the
adjusted command and its output.

## Deliverables
The document · `docs/ddd/README.ai.md` updated · a report giving the three counts, the proposed
respellings, and the convention-free names with the reason each is legitimately exempt.

## If you hit an unresolved decision
OPEN decision record, next free number from `decisions/INDEX.md`, stop, report. A §5.3 name that
cannot be resolved either way is exactly that case.
