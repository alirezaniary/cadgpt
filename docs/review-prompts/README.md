# Review prompts — for a second, more capable LLM

These five files are standalone prompts you hand-paste into a separate, more sophisticated
LLM session (one you have limited access to, and want to spend well). They are not run by
Claude Code and Claude Code does not read them back — they exist so a *different* reviewer,
with no memory of this project, can do a heavy structured review of it in one shot per layer.

Each file is self-contained: it can be pasted into a fresh chat on its own and will make
sense with only the context pack it names. You do not need to explain the project first —
each prompt carries its own primer.

## Order

Do them in this order. Each one is cheap to skip if you only have budget for a few, but the
order matters when you do more than one, because each layer's findings are what the next
layer should be checked against.

1. **`01-business-and-prd-review.md`** — is the product thinking itself sound? Contradictions
   in `prd.md`, gates claimed-measured vs. actually measured, scope drift against the stated
   non-goals.
2. **`02-architecture-review.md`** — do the structural contracts (import-linter, tenancy,
   layering, the three-valued status pipeline) actually hold, top to bottom?
3. **`03-backend-review.md`** — Django/DRF/Celery code, checked against a real bug history in
   report generation and dispatch that this repo already has.
4. **`04-frontend-review.md`** — React/TypeScript code, checked against the product's own
   stated frontend practices (polling discipline, RTL, generated types, Storybook coverage).
5. **`05-invariant-and-oracle-integrity-review.md`** — optional, but the highest-value single
   pass if you can only add one thing beyond what you asked for. It re-traces I1–I7 as one
   thread across engine → service → frontend, which the layer-by-layer reviews above can each
   miss individually even when each layer looks fine on its own.

## How to run one

1. Open the file. Follow its "Context to attach" section — it gives exact paths and, where
   the file would be too large to paste whole, a `sed`/`grep` command that trims it to the
   relevant slice.
2. Paste the prompt file's contents into a fresh conversation with the target LLM, then paste
   or attach the context pack after it.
3. If you're running these in order and want continuity, paste the *findings summary* (not
   the whole transcript) from the previous layer's run in before the context pack of the next
   one. Each file has a line noting where that goes.
4. Save the response. There's no fixed location required — a natural one is
   `docs/review-prompts/results/NN-<layer>.md`, gitignored or not as you prefer, since these
   are external findings, not something this repo's own build loop consumes.

## Docs are not the source of truth for what exists

Every prompt attaches documentation (`prd.md`, `docs/decisions.md`, `docs/stack.md`,
`CLAUDE.md`, `docs/ux/page-graph.md`) alongside source code, and some of the checklist items
ask the reviewer to check code *against* a doc's claim. That is a two-way check, not a
one-way one: a doc describes intent at the time it was written, and this project's own
development history shows docs falling behind the code they describe (statuses in
`docs/plan.md` marked done, a claim in `CLAUDE.md` about a mechanism that isn't the one the
code actually uses). Every prompt below now says this explicitly, but the principle applies
everywhere in every one of them:

- **The code is the source of truth for what currently exists.** A doc is the source of truth
  for what was *decided* and *why* — not for whether that decision is still what's on disk.
- **Treat every doc claim about current implementation as a hypothesis to verify against the
  pasted source**, not as a fact to check the code against. If the code and the doc disagree,
  report the disagreement itself as a finding — tagged as doc drift — regardless of which side
  turns out to be "right." The point is that they no longer agree, and someone downstream
  (a builder, a customer, this same reviewer next time) will trust whichever one they read
  first.
- This cuts both ways: a doc can also be *ahead* of the code (describing something as settled
  that the code doesn't yet reflect), which is just as much a drift finding as a doc lagging
  behind a change that shipped.

## Ground rules baked into every prompt

Borrowed from how this project already reviews its own work (`CLAUDE.md`, `docs/agents.md`):

- **Findings must cite a specific location and a specific consequence.** "Consider adding
  more tests" is not a finding. "Consider X" statements without a mechanism are asked to be
  dropped, not softened.
- **A green test suite is not evidence.** This repo has a documented history of suites
  passing while the real path was broken. Every prompt asks the reviewer to trace actual
  code paths, not infer correctness from test presence.
- **Distinguish "not built yet" from "broken."** This product is mid-build (Phase 3 of
  `docs/plan.md`); each prompt lists what belongs to a later phase so a reviewer without that
  context doesn't spend its budget re-discovering the roadmap.
- **Distinguish "different from convention" from "wrong."** `docs/stack.md` records
  deliberate rejections (no RLS, no Redux, no SSR, findings as a JSON document rather than
  rows). Each prompt names the ones relevant to its layer so they aren't re-litigated as
  oversights.
