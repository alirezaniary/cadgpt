# INBR Haiku remediation — COMPLETE (2026-09-19)

All 190 templated chunks identified in `docs/inbr-haiku-remediation-runbook.md` have been
replaced with real per-record analysis and mechanically validated. Final state, verified
by running the runbook's `verify.py` against this checkout just now:

```
real=667 stub=0 total_seen=668
remaining stub chunks: []
```

`total_seen=668` vs `real=667`: chunk 42 is the pre-existing JSON-parse-error chunk called
out in the runbook as a separate, explicitly out-of-scope issue — not a stub, not part of
the 190. Everything the runbook asked for is done.

## Process (as executed to completion)

Ran under `/loop` dynamic mode. Each batch of up to 5 Haiku workers got one chunk each
(chunk number, absolute transcript path, schema path, full job spec including the
anti-invention instruction from chunk 347's earlier failure). For every result:

1. Coordinator (this session) ran `validate_chunk.py <N>` itself — schema + record-id
   coverage — never trusted the worker's self-reported "ok".
2. Coordinator independently checked reason/unsupported_reason string distinctness across
   the chunk's own items (anti-templating), not just relying on validate_chunk.py's
   internal check.
3. Before deleting any superseded stub file, coordinator loaded it and confirmed by content
   (the stub's reason/unsupported_reason collapses to 1 of the 2 known template strings,
   repeated once per item) — never by filename or agent report alone.
4. Checked `stat -c '%a'` on every new file; all landed at 0600 as instructed, no chmod
   fixups needed this round.

No failures in this session's batches (656, 658, 659, 660, 661, 664, 665, 666, 667) — every
worker's first attempt passed mechanical validation and anti-templating on the first try.

## What's NOT done (explicitly out of scope, per the runbook)

- Chunk 42's JSON parse error — separate, pre-existing issue, untouched.
- The PostgreSQL import (`import_inbr_rule_extraction`) against the corrected
  `worker-drafts/haiku-pass-1/` output for all 43 documents — this is the next real step
  but was explicitly deferred until this remediation was complete and reviewed.
- English glossing, IDS compilation, publication — still `forbidden_downstream` per
  `tools/inbr_pipeline_status.py`.

## Next step if resuming this work

Re-run the Django import fresh for all 43 documents against `worker-drafts/haiku-pass-1/`,
then decide whether an `/adversarial-review` pass over a sample of the 190 corrected chunks
is warranted before treating this as production-ready (spot-checking real content quality,
not just mechanical schema/coverage, has not been done at scale — only chunk-by-chunk as
each batch landed).
