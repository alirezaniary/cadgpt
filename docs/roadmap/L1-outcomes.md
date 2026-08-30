# L1 — outcomes

Ten. Each is a state of the world the stakeholder can judge without reading code. Each is a
precondition for those below it.

This level is **fully enumerated**, per breadth-before-depth (`docs/process/decomposition.md`).
Only O1 is expanded to L2, because only O1 has no unbuilt prerequisite.

---

## v0 — the oracle

### O1 — We can tell an engineer, truthfully, what in their model is checkable and what is not
The model loads, is gated, is enriched with observations under named conventions, and the
system states — with real numbers — which required observations it produced and which it
could not, and why.

**Prerequisites:** none. **Startable now.**
**Judged by:** a coverage report on a real model from a real office.
**Answers:** `prd.md` §11 Gate 3 (derivability) and Gate 5 (what coverage actually says).
**Note:** clause-level coverage ("evaluated 12 of 80 provisions") needs O2. Observation-level
coverage ("produced 31 of the 40 observation types required") needs only O1, and is the honest
first number.

### O2 — The machine that turns regulatory text into executable rule packs works
The codification harness runs text through extract → review → classify → compile → fixture,
and the quote linter catches a draft whose encoded bound disagrees with its own source quote.

**Prerequisites:** O1's observation vocabulary — a rule must reference an observation type
that exists, or the missing-derivation guard cannot fire.
**Judged by:** a pack that compiles, audits clean, and runs its fixtures — built from **sample
and synthetic content**, not real regulation (DEC-0015).
**Not blocked by anything external.** Real regulatory content is loaded last, deliberately.
Synthetic packs prove the machine better than real ones can: they can contain a rule that must
return INDETERMINATE, a quote that contradicts its bound, and a requirement nothing produces —
none of which a real code supplies on demand.
**Later, on real content:** this harness is what answers `prd.md` §11 Gate 1 (review throughput,
and the size of the confident-wrong-PASS risk). That measurement happens when content is
loaded, not now.

### O3 — The right rules apply to this project
Basis resolution: four dates, adoption closure, overlays outermost to innermost, parcel
entitlements, project departures, declared conflict policy. Plus the parcel channel that two
of the highest-frequency v0 checks depend on entirely.

**Prerequisites:** O2 (there must be packs to resolve among).
**Judged by:** the same model resolving to different effective rule sets under different
dates and jurisdictions, with each difference explained.
**Partly blocked by:** `prd.md` §11 Gate 4 — can cadastral boundary and zoning envelope data
actually be obtained for a real parcel, in a joinable form. Currently assumed, not known. This
blocks the setback and site-coverage *checks*, not the resolver, which is built and tested
against synthetic parcel geometry like everything else.

### O4 — A run produces honest findings
The evaluation wrapper and the findings core: three-valued status and applicability, coverage
manifest, compliance routes, tolerance and margin, attribution, provenance.

**Prerequisites:** O1, O2, O3.
**Judged by:** a run over a real model producing findings an engineer argues with rather than
dismisses — and an `INDETERMINATE` set that is specific rather than a shrug.

### O5 — The engineer sees findings where they will act on them
Localized report with correct right-to-left rendering, web overlay with markers on elements,
marked sheets per storey, BCF underneath all three.

**Prerequisites:** O4.
**Judged by:** an architect opening the overlay and going straight to a fix.

### O6 — The engineer can fix their model before exporting
The read-only pre-flight tool inside the host, naming what is missing in their language with
jump-to-element, and driving the export with a correct preset.

**Prerequisites:** O1 (it reports the same missing-input taxonomy the gate does). Host choice
depends on Gate 2.
**Judged by:** `prd.md` §11 Gate 3's real question — how many of five real models pass only
after pre-flight, and how much work does it ask of the designer. Ten minutes is a feature; two
days is a different product sold to a different buyer.
**Note:** ships in v0. Without it the MVP's failure mode is refusing a file and leaving the
user with no way forward, which is not a product.

---

## Beyond v0

### O7 — The engineer can ask why
Chat over the results: why this clause applies, what would satisfy it, what changed between
code versions, what the cheapest fix is. Same engine, same findings, an agent in front of them.
**Prerequisites:** O4, O5. **= v1**

### O8 — The work happens inside their tool
The connector, read direction. Checks run from inside the authoring application, findings
placed as markers on elements in the user's own model. No file handover, no export lottery.
**Prerequisites:** O5, O6. **= v2. This is where the product becomes the role model.**

### O9 — The system authors
Typed generators, conversational parameter filling, geometry written into the live model and
checked by the O4 engine as its verifier.
**Prerequisites:** O8. **= v3.** A product transition, not a feature release: checking verifies
someone else's work; authoring means we produced the thing being judged, and the liability
posture changes with it.

### O10 — The system calculates
Verify an existing analysis against the standards; then preliminary sizing; then analysis.
**Prerequisites:** O4 only, for the verification tier — it is a checker, which the system is
already good at, and it needs no solver. May pull forward ahead of O9 if the structural corpus
is ready before the generators are. **= v4**

---

## The shape of the order

```
O1 ─┬─▶ O2 ──▶ O3 ──▶ O4 ─┬─▶ O5 ──┬─▶ O8 ──▶ O9
    │                      │        │
    └─▶ O6 ────────────────┘        │
                           └─▶ O7 ──┘
                           └─▶ O10
```

O1 is the only node with no unbuilt prerequisite. Under `docs/process/decomposition.md`
Rule 2, it is the only node that may be started.
