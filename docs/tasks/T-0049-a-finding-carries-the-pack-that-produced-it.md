# T-0049 — Every finding carries the pack identity and version that produced it

**Phase:** 3   **Status:** open
**Touches invariants:** I5 (a finding cites its authority), "never assert compliance we did not
establish". **Reviewer-gated.**

## Why

Found by the T-0031 review. `prd.md` §5.7 is explicit: *every finding carries the pack identity
and version, because a finding asserts that a rule says something, under our name.*

T-0031's `_combine_reports` flattens every selected pack's specifications into one tuple with no
pack attribution, and `ReportView.tsx` renders them as one list. The selection appears as a block
at the top of the report, so the run says *which packs it ran*; an individual finding cannot be
traced back to the pack — or to that pack's `source_citation` — that produced it.

T-0031's Scope only promised "the run's recorded selection shown on the report", so the code is
scope-honest and the review said so. It is the *Why* that over-claimed, and this task is the part
that was actually promised by the PRD and not delivered. It matters most exactly where the
product is most exposed: a FAIL that an architect forwards to a client is an assertion that some
named rule, from some named source, says the thing. Right now the report can say which packs were
in the room; it cannot say which one spoke.

This is also what makes `RulePack.source_citation` (T-0030) reachable. Today it is a column with
real attribution in it that no report surface ever renders.

## Scope

**Changes**

- A specification in a combined report carries the identity of the pack it came from — uuid,
  name and version at minimum, sufficient to resolve to the recorded selection entry rather than
  duplicating it.
- The report surface renders that attribution on the finding, and reaches the pack's
  `source_citation` from it.
- The Markdown report (T-0032) carries it too. If T-0032 has landed by the time this is built,
  it is in scope here; if not, T-0032's task file gains the requirement.
- `REPORT_SCHEMA_VERSION` bump, and the fallback for documents stored before it, following the
  pattern T-0027 established: the fallback keys off field presence, not version number.

**What explicitly does not change**

- The engine. It checks one IDS file per call and does not know what a `RulePack` is; the
  attribution is applied where the several reports become one, in the service layer.
- The counts, the coverage sentence, the three-valued discipline.
- Findings as first-class rows with identity across runs — named in `docs/plan.md` Phase 4 and
  still deferred. This is attribution inside the one JSON document, not a new table.

## How to prove it ran

`make verify`, then against `make up`: a real multi-pack run whose report shows each finding
attributed to the correct pack — **with at least two packs that both produce findings**, so a
mis-wired attribution is visible rather than trivially correct. A stored pre-bump document still
renders through the fallback. Rendered browser evidence, and the resolved `source_citation`
reachable from a finding.

## Evidence

## Review
