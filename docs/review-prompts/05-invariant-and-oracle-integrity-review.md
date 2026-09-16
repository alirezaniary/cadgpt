# Prompt: invariant and oracle-integrity review (optional, highest-value single pass)

Paste everything below the line into a fresh conversation, then attach the context pack
described in "Context to attach." This prompt is designed to stand alone — it does not
require the other four to have been run — but it will find more if you paste their findings
summaries first, since it's specifically hunting for seams *between* the layers those four
each check individually.

---

You are auditing a single product claim across an entire codebase in one pass: that seven
named invariants actually hold in the shipped system, not just in its documentation. This
prompt is deliberately not organized by directory or framework, because the failure mode it
exists to catch is exactly the one a per-layer review misses — each layer looking correct on
its own while the seam between two layers quietly leaks. Hold the whole chain in your head at
once: engine → service → API → frontend.

**Docs are not the source of truth for what exists — the code is.** This entire prompt is
built around checking `prd.md`'s claims against the pasted source, which makes the general
rule specific here: every invariant below is a *documentation* claim until you've located its
enforcement mechanism in the code. "The document says X is enforced" and "X is enforced" are
different findings — keep them distinct in your table, and if you can only confirm the first,
say so rather than rounding up to the second.

## Why this matters more than a normal code review, for this product specifically

The product's own stated thesis (`prd.md` section 2) is that a wrong compliance answer
produces no error — the model opens fine, the drawing looks correct, and the mistake surfaces
at plan review or on site or never. So the seven invariants below are not style preferences;
they are the entire mechanism by which this product is safe to trust. Section 3 (I1–I7) and
section 5.7 (what a finding is) are, in the document's own words, "not a slogan — this is the
section." Treat your review the same way: a passed invariant here is worth more than a clean
finding anywhere else, and a violated one here matters more than every other finding in the
other four reviews combined.

## The seven invariants, verbatim from `prd.md` §3 and §5.7

- **I1** — The language model never evaluates a rule.
- **I2** — The language model never authors geometry freehand.
- **I3** — The product does not rebuild what the open ecosystem already ships.
- **I4** — The product is jurisdiction-agnostic; no code cycle or local standard is
  hard-coded anywhere in the engine.
- **I5** — Every finding cites a resolvable basis; every calculation cites a standard and
  shows its inputs.
- **I6** — No relationship with software vendors: public interfaces only, local install only.
- **I7** — The system never asserts compliance it did not establish. Status is three-valued
  (PASS/FAIL/INDETERMINATE) and INDETERMINATE never becomes PASS anywhere.

Only I1, I2, and the three-valued core of I7 have shipped enforcement surface in this phase
(the checking engine and the review app). I3 and I6 are largely dependency-selection
disciplines to check against `docs/stack.md`'s inheritance table. I4 is live and testable
right now because Phase 3 is actively integrating real rule packs. I5's citation chain is
partially implemented (see the task list below).

## Context to attach

1. `prd.md` sections 3 and 5.7 — paste verbatim (you may omit the rest of the document).
2. `packages/engine/src/cadgpt_engine/` — every file, and `packages/engine/tests/` — every
   test file (small package; paste whole).
   `find packages/engine -type f -name "*.py" -not -path "*__pycache__*" | sort | xargs -I{} sh -c 'echo "=== {} ==="; cat {}'`
3. `services/api/cadgpt/apps/review/services/execution.py`,
   `services/presentation.py`, `report_generation.py`, `report_markdown.py`,
   `review/applicability.py`, `review/requirements.py`, `review/disclosure.py`,
   `review/choices.py`, `review/reasons.py`.
4. `services/api/cadgpt/apps/review/api/urls.py` and whatever serializer/view file it routes
   to for the run-detail and report endpoints.
5. `services/web/src/api/types.ts` and `services/web/src/features/review/ReviewDetailPage.tsx`.
6. The `[tool.importlinter]` section of `pyproject.toml`.
7. Grounding for I4 (live risk right now): `docs/tasks/T-0044-seeding-real-packs.md` and
   any other task file matching `*pack*` or `*catalogue*` under `docs/tasks/`:
   `ls docs/tasks/ | grep -iE 'pack|catalog'`, then cat the matches.
8. Grounding for I5 (citation chain): `docs/tasks/T-0026-*.md`, `T-0027-*.md`, `T-0039-*.md`,
   `T-0049-*.md` — the requirement-description, structured-citation, citation-subject, and
   finding-carries-pack tasks.

## What to do

For each invariant, produce a **mechanism-and-gap table row**: what specifically enforces it
today, and where the nearest plausible violation would enter. Don't just say whether it holds
— show the reasoning.

1. **I1.** Import-linter contract 1 blocks import-time reach from `cadgpt_engine` into an
   inference client. That closes one path. Is there a *data-flow* path around it: could a
   value a human typed after seeing an LLM's suggestion (a "declared" fact, per `prd.md`
   §5.7's provenance note — "extracted, identified, or declared") enter the evaluation
   pipeline indistinguishably from a measured value? Trace where declared facts are stored
   and consumed, and check whether findings resting on one are actually marked as such
   wherever they surface, per the PRD's own requirement.
2. **I2.** Not yet applicable in this phase — there is no generation/authoring code in this
   codebase yet (`prd.md` §5.11 is v3). Confirm that's actually true (search for any geometry
   *writing* code, as opposed to reading/measuring) and state it as a clean "not yet
   applicable" rather than searching for a violation that can't exist yet.
3. **I3.** Cross-check `docs/stack.md`'s inheritance table against `pyproject.toml`'s
   dependencies and `packages/engine/`'s actual code. Is there any hand-rolled logic in the
   engine that duplicates something `ifcopenshell`/`ifctester`/the inherited stack already
   does, rather than calling it? A reimplementation-in-miniature is the specific failure mode
   to look for, not "did they use the right library name."
4. **I4 — live risk.** Search the *entire* repository, not just the engine, for a hardcoded
   country name, jurisdiction string, clause number, or code-specific magic number
   (dimension, ratio, count) living outside pack content or test fixtures. Phase 3 is
   actively seeding real Iranian rule packs (`T-0044`) — this makes I4 a present-tense risk,
   not a hypothetical one. Check `review/applicability.py` and `rulepack/` particularly:
   does any selection or default logic assume a specific jurisdiction's rule shape?
5. **I5.** Pick one finding type and trace it from `ifctester`'s raw JSON output, through
   `report_generation.py`, to what actually reaches the API response and the rendered report.
   Does the clause citation survive every hop, or is there a point where it's summarized away
   (e.g., a rule name shown without its clause reference, or a citation present in the PDF but
   dropped from the JSON API response, or vice versa)?
6. **I6.** This is a business/process invariant more than a code one at this phase (no
   connector exists yet). State plainly that there's nothing in this codebase yet that could
   violate it, rather than manufacturing a finding.
7. **I7 — the core trace.** This is the most important row. Walk the full path a status value
   takes, end to end: `cadgpt_engine/status.py`'s three-valued type → how `execution.py`
   stores the result → any place `presentation.py` or the API serializer computes a count,
   percentage, or default filter → the type in `api/types.ts` → every place
   `ReviewDetailPage.tsx` renders, sorts, filters, or aggregates it. At every single hop,
   state explicitly whether INDETERMINATE is preserved as a distinct value or could collapse
   into PASS or FAIL, or vanish from a count. This is the one trace in this whole set of five
   prompts most worth getting exactly right — spend the most effort here.
8. **Coverage manifest and margin/tolerance (I7's stated sub-mechanisms).** `prd.md` §5.7
   describes a coverage manifest, tolerance-and-margin reporting, and route classification
   (prescriptive/deemed-to-satisfy/functional) as part of what a finding must carry. Which of
   these does the *current* implementation actually produce, versus which are described in
   the PRD but not yet built? State this split explicitly — the goal is to separate "not
   implemented yet, correctly deferred" from "claimed as done but isn't," since conflating
   the two would either alarm the user over a non-gap or hide a real one.

## What NOT to flag

- Anything about code style, naming, or structure that doesn't bear on one of the seven
  invariants — this prompt has one job.
- I2/I6 violations you have to invent because no relevant code exists yet — say "not
  applicable at this phase" instead of manufacturing a finding to fill the row.

## Output format

One table, one row per invariant: **Invariant | Enforcement mechanism found | Gap or risk
found | Severity | Applicable at this phase?**. Follow the table with the full I7 trace
written out as a numbered sequence of hops (not prose), since that's the artifact most worth
reusing later even if every hop is clean.
