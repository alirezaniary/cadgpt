# readme.ai.md — decisions/

## Purpose
The engineering decision log. Every decision, whoever made it, with the problem that forced it,
the constraints that bounded it, what we expect to observe if it was right, and what would make
us revisit it.

A decision reached in conversation and not written here did not happen, and will be
re-litigated differently by an agent that cannot see that conversation.

## Contract
- `INDEX.md` — the map, including which decisions are OPEN and who resolves them.
- `TEMPLATE.md` — the required shape. Seven sections, all of them.
- `DEC-NNNN-<slug>.md` — one decision each. Numbers are never reused.

**Scope.** This directory holds **engineering and process** decisions. `prd.md` §12 is the
closed log of **product** decisions and is never copied into here — a record may reference a
§12 entry and add an engineering consequence, never restate it.

## Invariants upheld here
- One decision, one file, one number, one copy.
- A record with no cost in "Consequences accepted" is describing a preference. Rewrite it.
- An "Expected result" that is not falsifiable is not an expected result. "Better
  maintainability" fails; "the engine environment resolves no inference SDK, provable by an
  import probe in CI" passes.
- `Status: OPEN` means no Decision line exists yet. An OPEN record with a decision in it is a
  contradiction and a defect.

## How to run it
Not runnable. Read `INDEX.md` first; its Open table is the only part that requires action.

## When to write one
- A Task session hits something unresolved → OPEN stub, then stop (DEC-0018).
- The Lead makes a choice a future session could reasonably make differently.
- Evidence contradicts a `prd.md` §12 decision at its printed Reopens condition → a record here
  referencing it, taken to the stakeholder.
- **Not** for choices with one obvious answer and no cost. A log padded with non-decisions
  stops being read, and then the real ones are not read either.

## Open questions
None. DEC-0015 closed: real regulatory content is loaded last, and the pipeline is built and
proven against sample and synthetic packs.
