# T-0106 — One authoritative rule-extraction draft per chunk, chosen by a written rule

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
**Touches invariants:** never assert compliance we did not establish

## Why

`.cadgpt/inbr/worker-drafts/` holds **900 files** matching `chunk-<N>-extraction.json` across
about 90 worker directories, covering **668 distinct chunks**. **209 chunks have more than one
draft file**, and nothing in the repository says which one wins. The Django importer
(`services/api/cadgpt/apps/inbr/management/commands/import_inbr_rule_extraction.py`) takes
exactly one `--extraction` path per invocation and contains no selection logic at all — the
choice was made by whatever ad-hoc loop drove it, and was made badly: the side dump in the
`inbr-dump-pg` container imported **2,204 of its 3,346 rule candidates (66%) from the
`rule-worker-a`/`b`/`c` templated stub drafts**, verified 2026-09-19 by grouping
`rule_candidate.extraction_file_uri`.

Every task after this one reads "the drafts". Until one deterministic index says which file is
authoritative for each of the 668 chunks, "the drafts" is 900 files with silent duplicates and
a two-thirds chance of picking a stub. This is also the invariant boundary: choosing a
templated draft over a real one means compiling a rule whose stated reasoning was never
derived from the source text.

The stub-detection method already exists and is reproducible — the verification script in
`docs/inbr-haiku-remediation-runbook.md`, which classifies a file by whether its
`reason` / `unsupported_reason` strings are one of three known hardcoded Persian sentences. Run
verbatim against this checkout on 2026-09-19 it reports `real=667 stub=0 total_seen=668`, with
chunk 42 the single chunk having no parseable draft.

## Scope

A committed tool and a generated index, not a one-off script run by hand.

- `tools/inbr_draft_index.py` (new) — walks `.cadgpt/inbr/worker-drafts/`, skipping `previews/`,
  and emits a JSON index: for each chunk number 1–668, the chosen file's path and SHA-256, the
  chunk's `structured_transcript_path` resolved from
  `.cadgpt/inbr/extraction/revision-2026-09-09-paddle/ledger.json` (`jobs[N-1]`, `chunk_order`
  is 1-indexed and matches array position), the rejected candidates with the reason each was
  rejected, and an explicit `unresolved` list. Deterministic: the same tree gives the same
  index, byte for byte.
- **The selection rule, written down in the tool's module docstring and applied there.** The
  recommendation: reject any file that fails to parse; reject any file classified templated by
  the runbook's three known stub sentences; reject any file whose `items` `record_id` set does
  not exactly equal the transcript's `sections` `record_id` set; among survivors prefer the
  newest by directory generation (`haiku-pass-1` over the earlier worker directories), and if
  two survivors remain tie-break on the lexicographically smallest path so the result is stable.
  If the builder finds a better rule, change it and say why in the evidence — but the rule must
  be in the code, not in the runner's head.
- **Chunk 42 must appear in `unresolved` with its parse error, not be silently dropped.** The
  index's own summary must state `chunks_resolved` and `chunks_unresolved` and they must sum to
  668.
- The index is written under `.cadgpt/inbr/` (git-ignored, mode 0600 under a 0700 parent, like
  every other artifact in that tree). The **tool** is committed; the index is data.
- `tools/` is outside the type gate per T-0066; match whatever that task settled rather than
  inventing a new convention.

**Does not change:** any draft file. This task only chooses among them. It does not import
anything into PostgreSQL and does not touch the `inbr-dump-pg` container.

## How to prove it ran

`make verify`, then the real path over the real tree:

```sh
.venv/bin/python tools/inbr_draft_index.py \
  --worker-drafts .cadgpt/inbr/worker-drafts \
  --ledger .cadgpt/inbr/extraction/revision-2026-09-09-paddle/ledger.json \
  --out .cadgpt/inbr/draft-index.json
```

The output must show `chunks_resolved + chunks_unresolved == 668` and name chunk 42 as
unresolved. Then paste, from the generated index:

- the count of chunks where more than one draft file existed (expected around 209) and, for one
  named example, which file won and why the others lost;
- the total number of files rejected as templated;
- proof of determinism: run it twice into two paths and show equal SHA-256 sums;
- a cross-check that no chosen file is under `rule-worker-a/`, `rule-worker-b/` or
  `rule-worker-c/` unless the index also records why that file passed the stub test.

## Evidence

<!-- the builder writes this -->

## Review
