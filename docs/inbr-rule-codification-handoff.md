# INBR rule-codification coordinator handoff

Written 2026-09-19, updated same day after T-0107 landed, for a fresh session to pick up the
coordinator loop. Goal: real, compiled, source-cited IDS rule files from the INBR corpus,
fastest safe path. Read `docs/agents.md` first — it is the coordinator/builder/reviewer
contract this whole loop runs under, including two rules added this session:

- **"Heavy per-record text passes are Haiku work, not builder work"** — directly governs the
  next task, T-0108.
- **"Fix-now dispatch is a fresh builder against the same task file, never `SendMessage` to the
  original builder's agent"** — added *after* this session's own coordinator made that mistake
  on T-0107's fix-now round (see `docs/decisions.md`, 2026-09-19, "fix-now findings dispatch to
  a fresh builder"). `SendMessage` to a terminal agent replays its entire original transcript as
  input tokens before the fix even starts; a cold `Agent()` call re-reading the task file is a
  fraction of that cost. Do not repeat this.

Then read `docs/plan.md`'s INBR section (route) and `docs/decisions.md`'s 2026-09-19 entries
(why). Don't re-derive the zip-backup/design-supersession history — it's in this project's
auto-memory (`inbr-pipeline-state-2026-09-19.md`) and in `docs/decisions.md`.

## Git state

`main`, HEAD `3131562` ("Clarify fix-now dispatch: same task file, never resume the original
builder"). Working tree clean as of this handoff.

## Task queue status (docs/tasks/T-0105 .. T-0111)

1. **T-0105 (one IDS compiler)** — **DONE**, committed `9c5c342`.
2. **T-0106 (authoritative draft-per-chunk index)** — **DONE**, committed `0feb396`.
3. **T-0107 (candidate-to-compiled-IDS command)** — **DONE**, committed `663ec32`.
   `candidate-to-rule-ir` CLI subcommand joins a provisional candidate to its
   `make_transcript_citation`-verified citation and a committed IFC-target mapping
   (`ifc-target-mapping.schema.json`), producing rule IR for `compile-native-rule`. Proven
   end to end on all 6 chunks of one real document: 28 candidates, 2 mapped / 26 unmapped
   with reason codes, both compiler branches (property and attribute) compiled to real
   `.ids` files and parsed by `ifctester`. Reviewed; one fix-now round closed (evidence had
   falsely claimed both compiler branches were exercised by the original two-entry mapping —
   both were actually property-shaped; a third real attribute-shaped mapping entry was added
   and compiled for real to close the gap).
   - **Judge observations, logged in the task file's Review section, not acted on** (don't act
     on these unless the judge prioritizes them): a same-`rule_key` collision across two
     candidates aborts `candidate-to-rule-ir` mid-write and drops that batch's `unmapped.json`
     — never fired on this 28-candidate document but a real risk at T-0108's 484-candidate
     scale; the CLI subcommand itself has zero test coverage (`_load_batch_root`, output
     layout, summary line are exercised only by manual/real-path runs, not `main()`); a mapping
     entry that matches no candidate is silently unreported (a `rule_key` typo would look
     identical to a genuinely unmapped candidate — matters directly for T-0108); unmapped
     records carry no page/text anchor for T-0109's reporting; the released `.ids`'s
     `book_title_fa` reads "Volume 23" on a Volume-24 document (pre-existing transcript defect,
     first carried into a release artifact by this task); nothing checks a mapped candidate's
     `implementation_type` against what the compiler can actually express.

4. **T-0108 (the IFC mapping table)** — not started. **Unblocked — dispatch next**; both
   dependencies (T-0105, T-0107) are done. Depends on T-0105 + T-0107.
   **Must be dispatched per `docs/agents.md`'s Haiku-worker rule** — 484 `native_ids`
   candidates, batched per document, 3-5 Haiku workers concurrent, one candidate/small batch
   each, coordinator independently re-validates every mapping against the candidate's actual
   Persian `statement_fa`/quote before accepting, rejects/redoes any batch where a mapping
   shape or phrase repeats across >2-3 candidates, and treats a zero-declined batch as suspect.
   The task file (`docs/tasks/T-0108-the-ifc-mapping-table.md`) already states this explicitly.
   **Before writing worker batches, read T-0107's judge observations above** — in particular:
   design the mapping-authoring batches so a `rule_key` typo or collision surfaces immediately
   rather than silently landing as "unmapped" or aborting a compile run later; consider whether
   T-0108's own evidence should note whether it hit the same-`rule_key` collision path.

5. **T-0109 (compile the corpus, publish what didn't compile)** — not started, depends on
   T-0108.

6. **T-0110 (citation granularity)** — not started, gates nothing, can run after T-0109.

7. **T-0111 (reimport projection)** — not started, explicitly off the critical path.

## Coordinator mechanics to remember on resume

- Dispatch Sonnet `builder` agents with just the task file path — it's self-sufficient by
  design. Gate a `reviewer` (Opus) dispatch only when a task touches an invariant, is a
  milestone boundary, has a weak/incomplete evidence block, or is too large to read in full.
- Two-pile findings triage: **fix-now** (invariant violated or evidence block false — same
  task file, fresh builder `Agent()` call, no re-review after) vs. **judge observation**
  (everything else — report it, do not self-file a task for it).
- **Fix-now dispatch is always a fresh `Agent()` call against the task file, never
  `SendMessage` to the original builder's agent id.** This is the rule this session's
  coordinator got wrong on T-0107 (see above) — don't repeat it.
- T-0105 and T-0106 were dispatched in parallel because their file scopes are disjoint — this
  session has no isolated worktrees, so builders share one working tree; only parallelize tasks
  after confirming disjoint file scope from the task files' own Scope sections.
- Commit only a task's own settled files. Never commit another in-flight task's uncommitted
  working-tree changes by accident (`git add` explicit paths, not `-A`, while more than one
  builder — or a peer session — may be touching the tree; this session found a peer session's
  live edit to `docs/agents.md`/`docs/decisions.md` mid-loop and correctly left it alone rather
  than folding it into T-0107's commit).
- Watch a builder's token usage where visible (`ListAgents`) against the 180k-220k budget in
  `docs/agents.md`; a builder well past that budget with no handoff is a signal the evidence
  block may need extra scrutiny, not just a throughput curiosity — this is exactly what
  happened on T-0107 (builder ran ~313k tokens, no handoff, and its evidence block did contain
  two false claims the reviewer caught).

## Also persisted this session, not directly part of the task queue

- `docs/agents.md` gained the "Heavy per-record text passes are Haiku work, not builder work"
  section (prior session) and the "fix-now dispatch is a fresh builder, never `SendMessage` to
  the original agent" clarification (this session, committed `3131562`) — both general process
  rules, not INBR-specific.
- A non-blocking context-budget hook for builder/reviewer subagents was added (commit
  `293cf90`, by a peer session running concurrently) — check its behavior if a builder's
  context-budget handling seems different than described above.
- Project memory `inbr-pipeline-state-2026-09-19.md` has the fuller narrative (zip-backup
  usage, design supersession, the deferred cross-check answer) if a fresh session needs the
  "how did we get here" context this file deliberately omits.
