# L0 — the goal

> **An engineer's design is verified against the regulations in force for it,
> deterministically, with every verdict citing a resolvable basis and every gap in
> coverage named.**

One sentence. It does not change.

## Reading it

**"the regulations in force for it"** — not "a rule set someone configured". Which
regulations apply is itself computed: from four dates, an adoption closure, jurisdiction
overlays, parcel entitlements and project departures. That computation is core domain, not
setup.

**"deterministically"** — the same model and the same pack versions produce the same result,
forever, with no language model in the path. This is I1, and it is why the product can be
argued with in front of a plan reviewer.

**"citing a resolvable basis"** — a clause, an entitlement instrument, or a departure. An
uncited finding is a bug, not a lesser finding (I5).

**"every gap in coverage named"** — the half that is easy to drop and impossible to retrofit.
A system that reliably reports what it could not determine is usable at seventy percent
coverage, because the user knows *which* seventy percent. A system that silently passes is
not usable at ninety-five.

## What this goal is not

It is not "check buildings automatically". That framing loses the second half of the sentence
and, with it, the only property that makes the first half safe to sell.

It is not "design buildings with AI". Design is downstream — `prd.md` §2: the design agent is
what becomes possible once the compliance engine exists. Building it first means building an
authoring system with no oracle, which is the thing this product exists as an alternative to.
