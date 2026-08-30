# Inherited test assets

Sources of sample models and sample rules, so no fixture work starts by authoring what already
exists (I3). Verified 2026-08-30.

**Read "What this clears" before assuming this clears anything.**

Selection here is on technical merit alone. Licence and legal questions are out of scope for
this repository (DEC-0021).

## Rules — sample IDS

| Asset | Where | Why it matters |
| --- | --- | --- |
| **250+ paired `.ids` + `.ifc` test cases** | `buildingSMART/IDS` → `Documentation/ImplementersDocumentation/TestCases` | **The single most valuable asset here.** Each pair is a rule plus a model it is meant to pass or fail. That is precisely the shape our evaluation wrapper and compiler need to be tested against, authored by the people who wrote the standard. |
| Sample IDS files | `buildingSMART/IDS` → `Documentation/Examples` | Small readable specimens — e.g. "project name must be TEST", "all walls must have a fire rating property". Good first targets for the YAML→IDS compiler. |
| The XSD itself | `buildingSMART/IDS` → `Schema/ids.xsd` | The format contract. Our compiler's output validates against this before IDS-Audit-tool ever runs. |
| Regulatory property definitions + localisation outline IDS | buildingSMART bSDD, Regulatory Information Requirements (UCM 3378) | The pack template and the property vocabulary we adopt before authoring our own (DEC-0019). Registration required. |
| Community IDS/BCF/IFC samples | `buildingsmart-community/Community-Sample-Test-Files` | Wider variety. Explicitly **not** official, and most do not pass the buildingSMART validation service — which makes them useful as *gate* test material rather than as clean input. |

## Models — sample IFC

| Asset | Where | Character |
| --- | --- | --- |
| Official sample test files | `buildingSMART/Sample-Test-Files` | Per-class, per-concept coverage. Unit-level. |
| IFC4.3.x sample models | `buildingSMART/IFC4.3.x-sample-models` | Larger models, infrastructure-leaning. Relevant to v5, not v0. |
| **Duplex Apartment** | `MadsHolten/BOT-Duplex-house` → `Model files/IFC/Duplex.ifc` | Created by USACE ERDC and the buildingSMART Alliance. The standard reference residential model — small, well-formed, carries spaces. Our default architectural fixture. |
| **Schependomlaan** | `jakob-beetz/DataSetSchependomlaan`; also in `ibpsa/project1-wp-2-2-bim` | A **real** Dutch project authored in Archicad by ROOT bv. Closest thing here to real office output, and the most useful model in this table for seeing how a genuine export behaves. |
| Assorted collections | `bimdata/BIMData-Research-and-Development` → `pages/IFC_FILES.md` | Index of models at various sizes, useful for performance work. |
| **IfcScript** | `buildingSMART/IfcScript` | Generates IFC example files programmatically. Directly relevant to DEC-0017 — study it before writing our own fixture generators. |
| Open IFC Model Repository | `openifcmodel.cs.auckland.ac.nz` | Listed in search results; **contents not verified** — the page did not return a catalogue on fetch. Check manually before relying on it. |

## What this clears, and what it does not

**Clears:** the entire build. Every capability from P0 through O5 can be built and proven on the
assets above plus synthetic packs. No real regulatory clause and no customer model is needed to
write a single line, which is DEC-0015 made concrete.

**Does not clear Gate 3 or Gate 5**, and this matters more than it looks.

Every model listed above is **curated**. It was authored carefully, exported deliberately, and
in most cases cleaned so it would serve as a good example. `prd.md` §5.2 names the largest
technical risk in v0 as export quality: *"a careless export omits IfcSpace entirely or ships it
without base quantities."*

A curated sample has had exactly that defect removed. So these models will make our derivation
layer look better than it is, and a coverage report over `Duplex.ifc` tells us nothing about
what a coverage report over a real office's file will say. Gates 3 and 5 exist to measure the
gap between those two numbers, and they can only be answered with **five real models from five
different offices** — which remains the one external dependency O1 has.

Using these samples as a stand-in for that measurement would reproduce, inside our own process,
the precise failure the product exists to eliminate: a clean-looking result over an unchecked
reality.

## Sources
- [buildingSMART/IDS](https://github.com/buildingSMART/IDS) — schema, examples, and the TestCases suite
- [IDS standard page](https://www.buildingsmart.org/standards/bsi-standards/information-delivery-specification-ids/)
- [Regulatory Information Requirements (UCM 3378)](https://ucm.buildingsmart.org/en/use-cases/3378/en)
- [buildingSMART/Sample-Test-Files](https://github.com/buildingSMART/Sample-Test-Files)
- [buildingSMART/IFC4.3.x-sample-models](https://github.com/buildingSMART/IFC4.3.x-sample-models)
- [buildingSMART/IfcScript](https://github.com/buildingSMART/IfcScript)
- [buildingsmart-community/Community-Sample-Test-Files](https://github.com/buildingsmart-community/Community-Sample-Test-Files)
- [BOT-Duplex-house](https://github.com/MadsHolten/BOT-Duplex-house)
- [DataSetSchependomlaan](https://github.com/jakob-beetz/DataSetSchependomlaan)
- [BIMData IFC file index](https://github.com/bimdata/BIMData-Research-and-Development/blob/master/pages/IFC_FILES.md)
