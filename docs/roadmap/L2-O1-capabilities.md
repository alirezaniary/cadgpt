# L2 — capabilities of O1

> **O1 — We can tell an engineer, truthfully, what in their model is checkable and what is not.**

Expanded because O1 is the only outcome with no unbuilt prerequisite. This level is fully
enumerated; **no capability below is decomposed to L3 yet**, per breadth-before-depth.

Strictly ordered. Each depends on the one above it.

---

## P0 — The harness exists
*Precondition to all code, not a capability of O1.*

`make verify` runs all sixteen gates over an empty repository and passes. Each guard is real —
a jurisdiction guard that matches nothing yet still parses `src/`, a placeholder scan that
scans, a test-balance check that reports 0/0 without dividing by zero.

**Why first:** guards added after code find violations in things that already have dependents.
Added first, they find violations in the diff that creates them.
**Evidence:** `make verify` exits 0 on an empty tree; each gate's line quoted from the Makefile;
each gate demonstrated failing on a deliberately bad input.
**Watch for:** a gate that passes because it silently found nothing to check. Every gate ships
with a proof that it fails when it should.

---

## C1.1 — The observation vocabulary exists and is enforced

The `Observation` value object; the three kinds; the convention naming scheme; the property
vocabulary from `prd.md` §5.3; construction-time rejection of a name carrying no convention.

**First move — inherit before authoring (DEC-0019).** Before defining a single property name,
check `prd.md` §5.3's `Pset_ACC_*` vocabulary against buildingSMART's bSDD regulatory property
definitions and adopt every term that already exists there. Ours is only the residue —
principally the convention-suffixed names a general vocabulary is unlikely to carry. If this
capability authors *more* names than §5.3 lists, I3 was violated.

**Why here:** it is the shared kernel. Derivation produces it, evaluation consumes it,
compilation references it, and a structural-analysis producer of the same atom arrives in v4.
Everything downstream keys on this, so it is built once, first, and does not move.
**Evidence:** a property test that no `Observation` can be constructed with a
convention-less property name; the jurisdiction guard rejecting a name with a code reference.
**Watch for:** a "convenience" constructor taking a bare number. That is the beginning of the
end of I4, and it will look reasonable.

---

## C1.2 — A model file loads and is gated

Wire the inherited gate (buildingSMART validate, `ifc-gherkin-rules`). Translate its output
into our missing-input taxonomy — the same shape O6's pre-flight will report in.

**Why here:** nothing can be derived from a model that has not been read, and nothing honest
can be said about coverage without knowing what arrived.
**Evidence:** a real model in, a real gate report out, naming specific entities.
**Watch for:** repairing anything. The gate never guesses and never repairs. A "helpful"
default for a missing unit is invention (`CLAUDE.md` §2).

---

## C1.3 — Inherited derivations produce observations

The library-call column of `prd.md` §5.4: areas via `ifc5d.qto`, volumes and bounding
dimensions via `ifcopenshell.util.shape`, adjacency and routes via `topologicpy`, envelope via
`IFC_BuildingEnvExtractor`, georeferencing via `ifcgref`. Each as an `ifcpatch` recipe, each
independently runnable.

**Why here:** it establishes the recipe pattern and the write-back mechanism before any custom
geometry is attempted, and it is where most of the observations actually come from.
**Evidence:** each recipe run standalone from the CLI over a fixture, its written-back property
read off the model with its convention in the name.
**Watch for:** writing something the library already does (I3). Before any code here, the
question is whether the ecosystem ships it.

---

## C1.4 — Custom derivations produce observations

The five or six nobody has written: stair clear width, shaft plan area and proportion, parking
stall and maneuvering clearance, setback against zoning envelope, clear and floor-to-floor
height.

**Why here:** it depends on the recipe pattern C1.3 establishes, and it is the only genuinely
novel geometry in v0.
**Evidence:** each recipe standalone over an adversarial fixture — a stair narrowing at one
tread, a shaft that is not rectangular — with the measured value asserted against a
hand-computed one.
**Watch for:** the promotion rule. A derivation enters the shared set only at three rules
across two clauses. Below that it lives with its rule and is counted. Rules-per-derivation is
the one number that reveals whether this whole strategy is failing.
**Note:** setback needs the parcel channel, which Gate 4 has not answered. It is specified
here and built when Gate 4 lands, or O1 ships without it and says so.

---

## C1.5 — Required-versus-produced is arithmetic

The observation manifest: what a loaded requirement set needs, computed statically; what
derivation produced; the set difference. The missing-derivation build error — a requirement
naming an observation type no registered recipe can produce fails the build.

**Why here:** it needs both a requirement side and producers, so it comes after C1.4.
**Evidence:** a requirement set and a model in, three sets out — produced, missing with a
reason each, and not required. Computed by set difference, never by catching an exception.
**Watch for:** an exception path becoming the coverage mechanism. If a missing observation
surfaces as a caught error rather than a computed absence, coverage is a side effect of failure
handling and will be wrong in exactly the cases that matter.
**Note:** until O2 delivers ratified packs, the requirement side is a **declared observation
requirement set** — a list of observation types, which is not a rule pack and cannot produce a
finding. It produces honest derivability numbers and nothing more. This is stated in the
output, not glossed.

---

## C1.6 — The coverage report is something a human reads and believes

The presentation of C1.5 to an architect: what this model supports, what it does not, why not,
and what would fix it — in their language, with reading direction correct.

**Why here:** it is the artefact the stakeholder judges, and it is `prd.md` §11 Gate 5.
**Evidence:** a report on a real model, in front of a real architect, and their reaction.
**Watch for:** the actual risk, which is not technical. A first run against an unfamiliar model
may be dominated by things it could not determine. That is honest and it reads as failure.
Whether it lands as a coverage statement or as a broken tool is the single largest
product-design question in v0, and it cannot be answered without real numbers in front of a
real person.

---

## Order, and what it buys

```
P0 ──▶ C1.1 ──▶ C1.2 ──▶ C1.3 ──▶ C1.4 ──▶ C1.5 ──▶ C1.6 ──▶ ✦ judged
```

Strictly serial. C1.4 and C1.5 look parallelizable and are not: C1.5's set-difference
arithmetic is only meaningful once the producer registry is complete, and building it against
a partial registry means building it against an assumption about C1.4's shape.

That is the cost of Rule 2. What it buys: when C1.6 produces a number, every part of the chain
behind it was built against something real, so the number means what it says. In a coverage
report, that is the only property that matters.

## Not decomposed yet

L3 slices for P0 and C1.1 are written once the stakeholder confirms O1. Writing them now would
expand a branch before its level is settled, which is the failure
`docs/process/decomposition.md` Rule 1 exists to prevent.
