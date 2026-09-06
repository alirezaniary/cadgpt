# T-0081 — A failed run never says why

**Phase:** 3   **Status:** open
**Touches invariants:** "Never assert compliance we did not establish", indirectly. A run
that failed established nothing, and the screen currently says only that it ended — which
is the thinnest possible version of saying what was not checked.

## Why

Found by the workbench built in T-0079. `CheckRunSummary` carries `failure_reason` and
`failure_detail`, the server populates them, and **nothing in `services/web/src` renders
either** — verified by grep on 2026-09-06, whose only hits outside `api/types.ts` were the
fixtures written that day.

So a run that was killed for resource exhaustion, or that failed on an unparseable IFC,
reaches the architect as one word in a table cell: `ناموفق`. They are given no way to tell
"your model is too large for us" from "your model is malformed" from "our worker died" —
three situations with three different next actions, one of which is theirs to take and two
of which are not.

This matters more than a missing label because the failure path is the one where a user has
already lost something. They uploaded a 400MB model, waited, and got a word. The reason
exists, is already on the wire, and is already localized by the server — it is simply
dropped on the floor.

Reproduce: `Screens/Review/Detail/Run Failed` in the workbench. Its fixture carries
`failure_reason: "RESOURCE_EXHAUSTED"` and a Persian `failure_detail`, and the screen
displays neither.

Unrelated to T-0068, which is about `ApiError.fieldErrors` on the registration form. Both
are the same class of defect — a reason the server sent, discarded by the frontend — which
is worth noticing as a pattern, but they are separate code paths and separate tasks.

## Scope

**Changes**

- `services/web/src/features/review/ReviewDetailPage.tsx` — a failed run shows its reason.
  Where exactly is a judgement call for the builder: the run-history row is cramped, and the
  open run already has a region below the history where the report would otherwise be, which
  is the natural place for "this run produced no report, and here is why".
- `services/web/src/i18n/{en,fa}.json` — a heading for that region, if one is needed.

**The wording rule this must follow**

`failure_detail` is server-composed prose in the reader's language, exactly like
`reason_label` and `disclosure_text` (`docs/decisions.md`, "Report prose belongs to the
server, not to the frontend catalogue"). Render it as given. Do **not** build a frontend
lookup table from `failure_reason` codes to Persian sentences — that is the mistake
`docs/decisions.md` already names, and it would put the engine's vocabulary in two places.
`failure_reason` may be used for a `data-` attribute or an icon choice; it is not a
translation key.

**Check before writing**

`failure_detail` may be blank for some failures. Confirm against the server what is
guaranteed, and make the blank case say something true rather than rendering an empty
block — a failed run with no detail should still say more than the status word alone.

**Not in scope**

- Retrying a failed run. There is no such endpoint and this task does not add one.
- T-0068's registration field errors.

## How to prove it ran

Not the workbench alone — the workbench proves the rendering, the stack proves the reason
is real:

1. Against the live stack, force a genuine failure (the `WORKER_MEM_LIMIT` override in
   `deploy/compose.yaml` already used in the `claim_count` work drives a real
   `RESOURCE_EXHAUSTED`), and show the screen with the reason on it.
2. Add the blank-`failure_detail` case to `ReviewDetailPage.stories.tsx` and show both
   stories rendering.

Evidence must include the actual failing run's `failure_reason`/`failure_detail` as the
server returned them, beside what the screen displayed.
