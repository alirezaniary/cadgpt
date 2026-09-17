# T-0096 — `CHECK_RUN_MAX_CLAIMS`'s defence argues for 2 and keeps 3

**Phase:** 3   **Status:** open
**Touches invariants:** none — a comment-accuracy gap, not a behavioural one.

## Why

Found by T-0062's review. `CHECK_RUN_MAX_CLAIMS = 3`'s settings comment
(`services/api/cadgpt/config/settings/base.py`, rewritten by T-0062) defends the bound with
a transient-overlap argument: two correctly-sized checks can momentarily overlap on the
same worker and push combined RSS over the limit, a condition that resolves itself as soon
as one finishes, and "one retry is enough to benefit from that." First claim plus one retry
is 2, not 3 — the comment's own reasoning does not reach the number it is attached to.
The comment is honest that `3` is not frequency-derived (it says so explicitly, twice), so
nothing is fabricated; it simply doesn't explain the third claim, which is inherited
unchanged from before T-0033/T-0062 rather than justified by either.

## Scope

- Either tighten the comment to explain what the third claim actually buys beyond the
  transient-overlap case it argues for (a genuinely-defensible reason may exist — e.g.
  tolerance for one additional unrelated transient cause, such as a `postgres`/`redis`
  blip — state it if so), or change the reasoning to honestly land on whatever number its
  own argument supports, or state plainly that 3 is inherited from before this reasoning
  existed and is being kept as-is without a claim to it being derived from this argument.
- No behavioural change implied unless the reasoning genuinely concludes a different
  number is warranted — this task is about the comment matching its own argument, not
  about picking a new value by feel.

## How to prove it ran

The corrected comment, read back against its own logic: does the number the comment
lands on match the number its argument supports?

## Evidence

## Review
