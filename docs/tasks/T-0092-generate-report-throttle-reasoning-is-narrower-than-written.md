# T-0092 — the no-throttle decision on `generate_report` reasons about work-per-message, not queue depth

**Phase:** 3   **Status:** open
**Touches invariants:** none — the role floor T-0060 added is the actual mitigation, this
is a docstring-accuracy and residual-risk question, not a live incident.

## Why

Found by T-0060's review. `CheckRunViewSet.generate_report`'s docstring argues no throttle
is needed because `ReportGenerationService.generate` is idempotent and cheap after the
first render — true, but idempotence bounds *work per message*, not *messages enqueued on
the shared `checks` queue*. A MEMBER-or-above member looping the POST still enqueues N
`generate_report_file` tasks that sit FIFO ahead of real model checks on that same queue,
each cheap individually but each occupying a worker slot in sequence — the flood concern
the original Why section named, now bounded to an authorized population rather than
eliminated.

Separately, the "one real render per succeeded run" claim holds only once the first
`_attach` has committed. `ReportGenerationService.generate`'s own module docstring
("No transaction spans the storage write") deliberately drops the row lock across the
render + `MediaService.store` window; concurrent deliveries arriving inside that window
each pay a full render and storage write, with the losers' `_attach` deleting their own
`Media` afterward. This is a real, if narrow and worker-concurrency-bounded, race —
identical in shape to whatever `ReviewViewSet.check` already tolerates, not a new hole
this task introduced, but the docstring's reasoning states a bound tighter than what
actually holds.

## Scope

- Correct `generate_report`'s docstring (and, if written anywhere else, T-0060's own
  evidence characterization) to state the bound accurately: idempotent per eventually-
  committed state, not per message enqueued; and name the race window explicitly rather
  than implying none exists.
- Decide, explicitly, whether the queue-depth flood risk (an authorized MEMBER looping the
  POST) is worth a throttle now that the population is authorized, or whether it is
  accepted the same way `ReviewViewSet.check`'s identical `throttle_classes=[]` already is.
  If accepted, say why in `docs/decisions.md` rather than only in a docstring, since this is
  exactly the kind of settled reasoning CLAUDE.md asks to be logged.

## How to prove it ran

No code change may be required beyond the docstring correction — if so, say so and show the
corrected text. If a throttle is added, the usual proof: `make verify`, and an over-the-cap
POST loop showing the throttle firing.

## Evidence

## Review
