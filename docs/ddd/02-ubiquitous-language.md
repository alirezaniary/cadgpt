# Ubiquitous language

Binding. The name here is the name in the code, the schema, the API and the report. A
synonym is a bug, and a term used with two meanings in two modules is the specific defect
this document exists to prevent.

## The partition that matters most

Every noun in this domain falls on one side of a line, and putting one on the wrong side
compiles a jurisdiction into the engine and makes the second country a fork rather than a
configuration (I4).

> **Test:** if two authorities could disagree about it, it is a **role**.

Two authorities cannot disagree that a shaft is 2.1 m by 3.4 m. They routinely disagree
about whether it qualifies as a light well.

### Physical kind — observable, may be a field or property name

`Space`, `Stair`, `StairFlight`, `Shaft`, `Slab`, `Wall`, `Storey`, `Opening`, `Door`,
`ParkingStall`, `Parcel`, `Building`, `Site`, `ProgramUse` (a *declared intended* use — the
designer's statement, recorded as an input, not a determination).

### Code role — conferred by a code, assigned at check time, never stored

`habitable`, `egress component`, `light well`, `occupancy class`, `fire compartment`,
`storey-for-density-purposes`, `fire stair`, `means of escape`, `dwelling unit`.

A role is computed by a **selector** inside a rule pack, under that pack, carrying a
derivation trace. It is never a field, never a property name, never read from the input
file. A file labelling a stair as a fire stair records the designer's *claim*; it enters as
`ProgramUse` or as annotation evidence and remains an input to a selector, never a
substitute for one. IFC predefined types are treated the same way — they encode regulatory
readings we do not inherit.

One model checked under three codes receives three different role assignments for the same
element. That is the point.

## Core terms

| Term | Meaning |
| --- | --- |
| **Observation** | The single unit of comparison. `(subject, property, convention) → value`. The model side produces them; the rule side constrains them; the tuple is the join key. Three kinds and only three. |
| — **Measured** | From geometry or from analysis. Carries provenance and confidence. |
| — **Related** | A fact about two subjects. Where the graph lives. |
| — **Derived** | A role computed under a specific pack. Never stored, always carries its derivation trace. |
| **Convention** | The measurement rule under which a value is true — inside face, centreline, narrowest point, between handrails. Lives *in the property name*, because IDS matches a named property. A value without a convention is not a quantity. |
| **Claim** | A quantity that arrived in the input file. An exporter's stored area asserts a value under an unnamed convention. Enters as evidence; re-derived before any rule reads it. |
| **Derivation** | An `ifcpatch` recipe computing an observation and writing it back as a conventionally-named IFC property. Independently runnable, independently testable. |
| **Observation manifest** | The set of observations a loaded pack requires, known statically before anything runs. Required-vs-produced is arithmetic, not a feature. |
| **Clause record** | The authored YAML unit of a rule. Carries verbatim source text, the encoded parameter, and **the source quote the parameter was taken from**, beside it. |
| **Draft** | A model-proposed clause record. Not a record. Cannot compile, cannot ship. |
| **Ratifier** | The named person who accepted or corrected a draft. The attributable author of the interpretation. A finding citing a clause is an assertion about what that clause says; the ratifier is who made it. |
| **Rule pack** | The modular compliance unit and the only place a jurisdiction exists. A national code, a municipal rule set and an office QA checklist are the same object type. |
| **Adoption** | A jurisdiction's enactment of packs at editions, with overlays, a conflict policy, and a resolved normative-reference closure. |
| **Overlay** | A narrower jurisdiction's amendment of a parameter. Resolved outermost to innermost. |
| **Entitlement** | A binding constraint attached to a *parcel* rather than a text. A parameter source, keyed by parcel. Unusable without a recorded instrument. |
| **Departure** | A variance, dispensation, exemption or approved alternative granted to a *single project* by an empowered authority. A parameter source, keyed by project. |
| **Basis** | What a finding cites. A clause, an entitlement instrument, or a departure. Must be resolvable (I5). |
| **RegulatoryTimeline** | Four dates: application, issuance, original construction, work. Each applicability predicate names which one it keys on. A single date silently restricts the product to new construction. |
| **Compliance route** | `prescriptive`, `deemed-to-satisfy`, or `functional`. An unmet deemed-to-satisfy rule means the design does not follow *that route* — not that it is non-compliant. |
| **Tolerance policy** | Declared per rule, overridable by overlay, never a global epsilon. Distinct from code-mandated **rounding**, which is a property of the rule and applied exactly as stated. Routing and classifying thresholds get zero tolerance. |
| **Margin** | The signed distance between measured and required, reported on every finding. More useful than either verdict. |
| **Near-miss** | Within tolerance of a limit. A distinct visible outcome naming the tolerance applied — never silently resolved in either direction. |
| **Finding** | The unit of output and the thing a reviewer argues with. Status, applicability, basis, attribution, margin, route, provenance. |
| **Coverage manifest** | Per run: clauses in force under the resolved adoptions, clauses with ratified rules, clauses deliberately out of scope with a reason, clauses unrepresented. Presented *before* findings. |
| **Provenance** | How a project fact came to be. `extracted` \| `identified` (a human pointed, the system measured) \| `declared` (a human stated). Humans may identify; humans may not measure. |
| **Disposition** | A human judgement about a finding — accepted, waived, disputed, fixed. Authored against the **project**, never a run. Survives re-runs and re-attaches by stable finding identity. |
| **Run** | One evaluation. Reproducible from input model hash and pack versions alone. Carries no human judgement. |
| **Gate** | The server-side backstop that names missing entities or quantities before any rule runs. Never guesses, never repairs. Inherited. |
| **Pre-flight** | The read-only tool inside the user's authoring application that names what is missing *before* export, in their language, with jump-to-element. Never modifies the model. |

## Status vocabulary — closed sets

```
Status          PASS | FAIL | INDETERMINATE
Applicability   APPLIES | DOES_NOT_APPLY | UNDETERMINED_APPLICABILITY
Route           prescriptive | deemed-to-satisfy | functional
Provenance      extracted | identified | declared
Observation     measured | related | derived
```

The *reason taxonomy* attached to `INDETERMINATE` grows. The values do not.

## Terms deliberately absent

Words that will feel natural and must not enter the code:

- **"compliant" / "non-compliant"** as a computed field. The system produces findings with a status and a basis. Compliance is a conclusion a human draws from them.
- **"score", "grade", "confidence percentage"** as an output. Aggregating three-valued findings into one number destroys the distinction I7 exists to preserve.
- **"validate"** for what the checking engine does. Reserved for the inherited ingest gate, to keep the two apart.
- **"extract"** for derivation. There is no extraction step; the input model and the checked model are the same object. Derivation *enriches in place*.
- Any jurisdiction, code name or clause reference in an identifier. Fails the build.
