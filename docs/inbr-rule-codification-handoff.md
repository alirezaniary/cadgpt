# INBR rule-codification coordinator handoff

Written 2026-09-19 for a context clear mid-loop. Goal: real, compiled, source-cited IDS rule
files from the INBR corpus, fastest safe path. Read `docs/agents.md` first — it is the
coordinator/builder/reviewer contract this whole loop runs under, including the "Heavy
per-record text passes are Haiku work" rule added this session. Then `docs/plan.md`'s INBR
section (route) and `docs/decisions.md`'s 2026-09-19 entries (why). Don't re-derive the
zip-backup/design-supersession history — it's in this project's auto-memory
(`inbr-pipeline-state-2026-09-19.md`) and in `docs/decisions.md`.

## Git state

`main`, HEAD `9c5c342` ("T-0105: one IDS compiler, not two (reviewed, fix-now round closed)").
Working tree clean as of this handoff.

## Task queue status (docs/tasks/T-0105 .. T-0111)

1. **T-0105 (one IDS compiler)** — **DONE.** Built, reviewed (all 5 headline claims verified:
   I1 kept, byte-identical attribute compile, real property-rule compile parsed *and evaluated*
   by the engine, `ids_compiler` fully gone, suites green), fix-now round closed and committed
   in `9c5c342`: H1 (`rule_relations.py`'s `_semantic_identity` crashed on property-kind rules)
   and H2 (`rule_capability.py`'s `classify_rule` wrongly deferred every property rule as
   `UNSUPPORTED_COMPARATOR`, which would have broken T-0108) are both fixed and re-verified.
   - **Logged, not acted on** (don't act on these unless the judge prioritizes them): H3
     (`rule_projection.py` rejects property sidecars — is T-0111's problem, off critical path),
     M1 (schema doesn't actually accept the documented `requirement_kind: "attribute"` default),
     M2 (a schema-rejection test assertion was weakened to a too-generic match), M3 (no
     `ifctester`-parse test for the property path), L1 (datatype/bounds not cross-validated,
     pre-existing, inherited from the retired `ids_compiler.py`).

2. **T-0106 (authoritative draft-per-chunk index)** — **DONE.** Built, reviewed, one fix-now
   round applied and verified, committed in `0feb396`. `tools/inbr_draft_index.py` is the
   committed tool; `.cadgpt/inbr/draft-index.json` is the live generated index (git-ignored,
   mode 0600 — regenerate with the command in the task file if it looks stale). **Load-bearing
   finding:** the corrected stub detector (it originally missed 2 of 5 templated-sentence
   variants) raised the honest unresolved-chunk count from 1 to **179/668**. This is real
   remaining-extraction work, not a new defect — it feeds T-0109's coverage manifest as
   `unresolved` chunks, which is exactly what that manifest exists to report honestly.

3. **T-0107 (candidate-to-compiled-IDS command)** — not started. **Unblocked — dispatch next**;
   both its dependencies (T-0105, T-0106) are done.

4. **T-0108 (the IFC mapping table)** — not started. Depends on T-0105 + T-0107. **Must be
   dispatched per `docs/agents.md`'s Haiku-worker rule** — 484 `native_ids` candidates, batched
   per document, 3-5 Haiku workers concurrent, one candidate/small batch each, coordinator
   independently re-validates every mapping against the candidate's actual Persian
   `statement_fa`/quote before accepting, rejects/redoes any batch where a mapping shape or
   phrase repeats across >2-3 candidates, and treats a zero-declined batch as suspect. The task
   file (`docs/tasks/T-0108-the-ifc-mapping-table.md`) already states this explicitly.

5. **T-0109 (compile the corpus, publish what didn't compile)** — not started, depends on T-0108.

6. **T-0110 (citation granularity)** — not started, gates nothing, can run after T-0109.

7. **T-0111 (reimport projection)** — not started, explicitly off the critical path.

## Coordinator mechanics to remember on resume

- Dispatch Sonnet `builder` agents with just the task file path — it's self-sufficient by
  design. Gate a `reviewer` (Opus) dispatch only when a task touches an invariant, is a
  milestone boundary, has a weak/incomplete evidence block, or is too large to read in full.
- Two-pile findings triage: **fix-now** (invariant violated or evidence block false — same
  builder, same task, no re-review after) vs. **judge observation** (everything else — report
  it, do not self-file a task for it).
- T-0105 and T-0106 were dispatched in parallel because their file scopes are disjoint — this
  session has no isolated worktrees, so builders share one working tree; only parallelize tasks
  after confirming disjoint file scope from the task files' own Scope sections.
- Commit only a task's own settled files. Never commit another in-flight task's uncommitted
  working-tree changes by accident (`git add` explicit paths, not `-A`, while more than one
  builder may be running).

## Also persisted this session, not directly part of the task queue

- `docs/agents.md` gained the "Heavy per-record text passes are Haiku work, not builder work"
  section — a general process rule, not INBR-specific, triggered by T-0108's shape matching the
  earlier 190-chunk remediation incident and now T-0106's own missed stub variant.
- Project memory `inbr-pipeline-state-2026-09-19.md` has the fuller narrative (zip-backup usage,
  design supersession, the deferred cross-check answer) if a fresh session needs the "how did we
  get here" context this file deliberately omits.
