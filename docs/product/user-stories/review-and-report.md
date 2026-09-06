# Review and report

Reconstructed on 2026-09-06 from T-0025 through T-0074, after the fact. This is the story
the product exists for; the other two are the way in.

**As a** architect who has just finished a model and is preparing to submit it for a permit
**I want** to be told which rules my model breaks, which it satisfies, and — separately and
unmistakably — which could not be judged from what I modelled
**So that** I fix what is actually wrong before a plan reviewer finds it, and I know exactly
how much of the rule set this check did *not* answer, rather than mistaking silence for
approval

## Acceptance criteria

- Given a project, when I add a review, then I supply a name and an IFC model and nothing
  else — the rule set is chosen per check, not per review.
- Given a model larger than the ceiling, when I upload it, then the number I am told is the
  number the server actually enforces, taken from its response.
- Given a review, when I choose one or more rule packs from the catalogue and run a check,
  then the button reports that a check is in flight and cannot start a second one.
- Given a check in flight, when I wait, then the page updates itself — I never reload to
  find out — and polling stops once the answer can no longer change.
- Given a finished check, when the report renders, then it states **first** what was
  checked at all (this model, by filename) and what was not (the drawing set), **then** how
  much of the rule set was evaluated, **then** the findings.
- **Given a specification that established nothing** — a schema mismatch, or one that
  matched no elements — **when coverage is computed, then it is excluded from the evaluated
  count and named in a list**, so the coverage line can read "4 of 6" and not the "6 of 6"
  that a count of statuses would always produce.
- Given findings, when they are ordered, then FAIL comes first and INDETERMINATE never sorts
  below PASS.
- **Given any count, summary or filter, when INDETERMINATE is displayed, then it is never
  folded into PASS** — it has its own column, at the same weight, with its own note saying
  these were not checked.
- Given the status filter, when I hide a category, then a banner states how many findings
  are hidden rather than resolved, and the three counts do not move.
- Given a check that succeeded but whose report file was not generated, when I open it, then
  I am told it is not generated *yet* and offered a retry — distinct from the case where it
  can never be generated, which says so and still offers the retry.
- Given a run that failed, when I look at it, then no partial report is shown.

## Explicitly out of scope

- Uploading my own IDS rule set. Removed from the UI on 2026-09-04; the catalogue is the
  only path.
- Dispositions — marking a finding accepted, waived or fixed. There is no identity for a
  finding across runs yet.
- The overlay: findings drawn on the model rather than listed. That is the product's
  eventual centre and is not built.
- Comparing two runs of the same review.

## Assumptions / open questions

- **Gate 5 in `prd.md` is unanswered and this story rests on it.** A first run against an
  unfamiliar model may be dominated by INDETERMINATE, which is honest and may read as a
  broken tool. Nobody has yet watched a real architect read one.
- A failed run currently shows its status and nothing about *why* — `failure_reason` and
  `failure_detail` are on the wire and not rendered on this screen. Whether that is a gap
  or deliberate is not recorded anywhere; see T-0079's findings.
- The catalogue picker's filter is free-text over jurisdiction/region/version. With four
  packs that is fine; with four hundred it is not a design anyone has tested.
