# MVP — v0

## What ships

The user provides a model file. The system gates it, derives, checks it against the loaded
packs, and returns a localized report plus a web overlay and marked sheets — **with every
check that could not run named explicitly.** No account, no authoring.

Plus the read-only pre-flight tool for the hosts Gate 2 identifies.

## Check scope

From `prd.md` §9, unchanged:

```
site coverage and density against the zoning envelope
setback
parking count, dimensions, maneuvering clearance
stair clear width, tread, riser, headroom
light well area and proportion
minimum room dimensions
floor heights
basic egress and fire separation
```

## Outcomes it comprises

| Outcome | Ships in v0 because |
| --- | --- |
| O1 · derivability and coverage | The oracle. Everything else is downstream of it. |
| O2 · codification harness | The engine is empty without a corpus, and the corpus must be producible, not hand-authored. |
| O3 · basis resolution + parcel | Site coverage, density and setback are among the highest-frequency rejection categories and cannot be checked without the parcel channel. |
| O4 · findings | The product's actual output. |
| O5 · report and overlay | A findings list is a document an architect skims; errors shown on the thing they just finished is something they act on. |
| O6 · pre-flight | Without it, v0's failure mode is refusing a file and leaving the user with no way forward. Using it is optional; building it is not. |

## What v0 deliberately does not have

| Absent | Why |
| --- | --- |
| An account system | Nothing in v0 needs identity. Adding one is a product surface with no v0 job. |
| The agent / chat | v1. The findings must be worth talking about before anything talks about them. |
| The connector's write direction | v2 and v3. Read is built first and completely. |
| Dispositions | Deferred with subject-identity-across-revisions, which is genuinely hard (`prd.md` §12). Findings are stateless in v0, and the re-check loop is correspondingly worse. Accepted, and stated. |
| Any 2D drawing input | Never. A 2D market is answered by Gate 2, not by a parser. |
| Any structural calculation | v4. |

## The bar for shipping

Not "the checks work". Three things, in this order:

**1. The coverage manifest is believed.** An architect reads "this run evaluated N of M
provisions, here are the ones it could not and why" and treats it as information rather than
as a broken tool. If this fails, no amount of check accuracy rescues v0 — the report is not
trusted and therefore not used. This is Gate 5, and it is a product-design question, not an
engineering one.

**2. Pre-flight costs minutes, not days.** Gate 3's real question. A pre-flight report cleared
in ten minutes is a feature. One taking two days is a different product, sold to a different
buyer, and it needs to be known before building rather than after.

**3. No finding is uncited, and no INDETERMINATE is anywhere reported as a pass.** I5 and I7.
Machine-checkable, and checked.

## The known risks, named

| Risk | Shape | Mitigation |
| --- | --- | --- |
| **Export quality** | Almost every check is space-based, and a careless export omits `IfcSpace` or ships it without base quantities. This is the single largest technical risk in v0. | Pre-flight at source, gate on arrival, partial results never silent, published export presets. Not by inventing the missing geometry — that is forbidden. |
| **Corpus arrives last** | Real regulatory content is deliberately the final work (DEC-0015), so the first genuine "N of M provisions" number arrives late. | The pipeline is proven against synthetic packs designed to break it — rules that must return INDETERMINATE, quotes that disagree with their bounds, requirements nothing can produce. Better coverage than real clauses would give. |
| **Parcel data unobtainable** | Gate 4 is assumed, not known. Two v0 checks depend on it entirely. | Answer Gate 4 before O3 starts. If unobtainable, those two checks become a declared out-of-scope entry in the coverage manifest — which is exactly what the manifest is for. |
| **The market is 2D** | Gate 2. v0's import path may have too few reachable users. | Twenty phone calls, before O6 chooses a host. If it happens, the recommendation in `prd.md` §11 stands: lead with authoring in a host we control. The corpus and engine are unchanged either way. |
| **Derivation set grows one-per-rule** | The failure mode of the entire inherit-don't-build strategy. | Rules-per-derivation tracked continuously; promotion gated at three rules across two clauses; the number is reported by the harness. Visible in one number, by design. |

## How v0 gets judged

Not by a feature list. By the three bar items above, on five real models from five different
offices, in front of a real architect.

Which means the thing that unblocks judgement is not code — it is five files. That request is
in `docs/roadmap/dependency-order.md` and it is the only external dependency O1 has.
