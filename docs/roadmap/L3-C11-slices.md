# L3 — slices of C1.1

> **C1.1 — The observation vocabulary exists and is enforced.**

Expanded after P0's L3, per breadth-before-depth: `docs/roadmap/L2-O1-capabilities.md` enumerates
every capability of O1, and C1.1 is the only one with no unbuilt prerequisite.

**Blocked until P0's evidence exists** — `make verify` exits 0 reporting nine registered gates,
each with a committed proof it can fail (`docs/roadmap/L3-P0-slices.md` §Done when). Rule 2 is
absolute; this file is the plan for after that, not permission to start before it.

## The shape

```
S1.1.1 ──▶ S1.1.2 ──▶ S1.1.3 ──▶ S1.1.4
inherit    the name    the atom    conflict
```

Strictly ordered, and the order is not arbitrary. The convention segments a name may carry are
whatever S1.1.1 finds already defined plus whatever it records as authored; deciding that set in
code before the audit is exactly the I3 violation DEC-0019 exists to prevent.

---

## S1.1.1 — The vocabulary is inherited, and what we author is only the residue

**Behaviour:** every property name in `prd.md` §5.3 resolves to either an existing buildingSMART
bSDD regulatory property definition, adopted by its bSDD URI, or a record saying we authored it
here and why nothing existing covers it. The result is committed data — a table, not code.

**Why first:** DEC-0019 and I3. `prd.md` §5.3 lists roughly thirty names, and the L2 note is
explicit that ours should be *the residue* — principally the convention-suffixed names a general
vocabulary is unlikely to carry. If this capability authors more names than §5.3 lists, I3 was
violated, and the only moment that is cheap to see is before any of them is written down as code.

**Evidence:** the committed audit, every row carrying a bSDD URI or an authored-here reason; the
count of adopted versus authored stated in the completion report.

**Watch for:** an audit that adopts nothing because bSDD was awkward to query. "Not found" is a
finding that must name the query that failed, not a default.

**Determinism note:** bSDD is a network service and gate 16 forbids a test that reaches it. The
audit is performed once, by hand or by a throwaway script, and its *result* is committed. Nothing
in `src/` or `tools/` queries bSDD at run time or at test time.

**Decision risk:** if the residue turns out large — if bSDD carries almost none of §5.3 — that is
a decision request about whether the convention-in-the-name scheme is as unusual as we assumed,
not a licence to author thirty names quietly.

---

## S1.1.2 — A property name carries its convention, or it does not exist

**Behaviour:** `NetFloorArea_InsideFace` parses into a base quantity and a named convention;
`Area` is rejected at construction with an error naming what is missing. The closed set of
convention segments is the one S1.1.1 settled.

**Why here:** it is the smallest thing that is true of every observation, and it is the invariant
`docs/ddd/04-aggregates-and-invariants.md` puts on `Observation` construction. Building the atom
first and adding the name rule afterwards means the rule is a validator over existing data rather
than a constructor precondition, and a validator can be skipped.

**This slice creates the first `src/` package**, and therefore **gate 3 (import contracts) ships
in the same task** — DEC-0022: a gate ships with the artefact type it guards, and the artefact
type "an `src/` module with a declared layer" arrives here. Gate 3 is what makes I1 and I2
statically enforced over *source*; gate 4 only proves it of the *environment*.

**Evidence:** every §5.3 name parses and round-trips; a bare name is rejected; gate 3 registered
and demonstrated failing on an `import anthropic` planted in `src/engine`.

**DEC-0028 cleared three defects out of gate 3's way before this slice was specified.**
`docs/ddd/05-import-contracts.md` named a layer `compilation` that is not a module, omitted
`observation` — the very layer this capability builds — from the layering entirely, and forbade
`generators.internals`, which does not exist and would have made `import-linter` error rather
than pass. The contracts in that file now resolve. Read the record before registering gate 3;
its §3 is a promissory note a later task owes back.

**Watch for:** the "convenience" constructor taking a bare number, named in L2 as the beginning
of the end of I4. It will look reasonable. It is not in this slice and is not in any later one.

**DEC-0026 meets a real layout here.** That record's Reopens-if turns on whether `src/engine`
needs an `__init__.py` of its own. Read it before creating the directory; if it does, `src/engine`
becomes a module directory owing a `readme.ai.md`, which is correct rather than an exception.

---

## S1.1.3 — An `Observation` is immutable, tuple-identified and three-kinded

**Behaviour:** `(subject, property, convention) → value`, plus kind, provenance and confidence.
`kind ∈ {measured, related, derived}`. A `derived` observation with an empty derivation trace is
rejected; a `measured` one with no provenance is rejected. Equality is the tuple, not the value.

**Why here:** it depends on S1.1.2's property name and on nothing else. It is the shared kernel —
derivation produces it, evaluation consumes it, and a structural-analysis producer of the same
atom arrives in v4 — so it is built once and does not move.

**Evidence:** a property test that no `Observation` can be constructed with a convention-less
property name; construction of each kind, and rejection of each kind missing what that kind owes;
gate 5 (jurisdiction) passing over the new module, which is the first time it has had real
`src/` source to scan rather than an empty tree.

**Watch for:** correction-by-mutation. A corrected measurement is a **new** observation; there is
no setter, no `replace`, no `with_value`.

---

## S1.1.4 — Two values for one tuple is a corroboration conflict, not an error

**Behaviour:** an observation set accepts two observations with the same tuple and different
values, keeps both, and reports the pair as a conflict. It does not raise, does not de-duplicate,
does not pick a winner and does not average.

**Why last:** it is the one behaviour of the set rather than the atom, and it is meaningless
until the atom's identity rule (S1.1.3) is fixed.

**Why it is in C1.1 at all:** `docs/ddd/04-aggregates-and-invariants.md` states it as an
invariant of `Observation` identity — "a corroboration conflict, which is a finding, not an error
to resolve". The *finding* is produced much later, in `engine/findings`. What belongs here is the
representation that makes producing it possible, and the refusal to resolve it. A set that
silently keeps the last write destroys the conflict before anything downstream can see it.

**Evidence:** two observations, same tuple, different values, in one set; both retrievable; the
conflict enumerable. No exception raised anywhere in the path.

**Watch for:** a `dict` keyed on the tuple. That is the silent last-write-wins, and it is the
obvious implementation.

---

## Done when

`src/engine/observation` exists with a conforming `readme.ai.md`; gate 3 is registered and has a
committed proof it fails; `make verify` exits 0 reporting **ten** registered gates; every §5.3
property name either carries a bSDD URI or an authored-here reason in committed data; and no
`Observation` can be constructed carrying a convention-less name.

## Not decomposed yet

L4 task specs. Written one slice at a time, in order, after P0's evidence exists — writing
S1.1.4's tasks now would expand a branch before the level above it is settled
(`docs/process/decomposition.md` Rule 1).
