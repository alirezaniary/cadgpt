# T-0106 — One authoritative rule-extraction draft per chunk, chosen by a written rule

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** built
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

**Correction, 2026-09-19 (build review):** the `real=667 stub=0` premise above is falsified.
The runbook's literal three-sentence match missed a fourth stub variant used by
`rule-worker-c` (1,393 items, all one sentence — identical to a known one except its last two
words) and, once generalized detection was built, a fifth variant found across other worker
directories too. See Evidence for the corrected count and the generalized (non-literal)
detector this task shipped instead.

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

**Built:** `tools/inbr_draft_index.py`. Selection rule is written in the module docstring and
applied in `evaluate_chunk`: reject `parse_error` (invalid JSON, fails
`provisional-extraction.schema.json` validation — reused via `cadgpt_regulations.jsonio`, not
reimplemented — or an empty `items` array), reject `templated` (see **Review fix C1** below —
this is no longer literal-string matching), reject `record_id_mismatch` (`items[*].record_id`
set ≠ transcript `sections[*].record_id` set), then among survivors prefer newest by file
`mtime` (documented deviation from a hand-maintained directory-generation table — see
docstring "This mtime-based rule is a deliberate deviation..." — mtime empirically separates
`haiku-pass-1` (2026-09-18) from every `rule-worker-*`/`luna-*` directory (2026-09-14 through
2026-09-16) without a table that would go stale on the next worker batch; **known limitation
H1 below**), tie-break on lexicographically smallest path.

### Review round 1 fixes

**C1 (invariant breach, fixed)** — the first version matched three literal hardcoded Persian
sentences, which missed `rule-worker-c`'s stub entirely: all 1,393 of its items share one
`reason` string differing from a known one only in its last two words (`بازبینی معنایی` →
`بازبینی منبع`), so all 150 chunks it supplied (350–499) were wrongly recorded as real.
Fixed by replacing literal matching with `_collapse_check`: reject any file where every item
carries a `reason`/`unsupported_reason` value and those values collapse to ≤1 distinct string
(with more than one item — see the tool's docstring and `_collapse_check`'s own docstring for
the full rule and why literal matching can't be complete). Re-run over the real tree, verified
below: those 150 chunks now have no other candidate and are `unresolved`, not re-stubbed to
anything else. The new detector caught more than just `rule-worker-c` while it was at it — see
"newly-discovered stub sources" below.

**C2 (circular evidence, fixed)** — the original "150 chosen files all pass stub_check" claim
checked the detector's own output against itself. It's fixed by the detector no longer having
that hole (C1), and the corrected evidence below is checked the same way but now against a
detector that has been shown to catch a stub source it previously missed, on real data, not
asserted. The runbook's `real=667 stub=0` premise the task file cited is corrected in "Why"
above, pointing here.

**H2 (fixed)** — `args.out.parent.chmod(0o700)` was unconditional, which would silently strip
permissions from a pre-existing, possibly-shared directory the caller pointed `--out` at
(`Path.mkdir(..., exist_ok=True, mode=...)` silently ignores `mode` when the directory already
exists, so the explicit `chmod` after it was the actual, unconditional culprit). Fixed: chmod
only fires when this run's own `mkdir` created the directory (tracked via `parent.exists()`
checked before `mkdir`). Reproduced both branches directly:
```
$ mkdir -m 0755 -p /tmp/t0106_h2_test && stat -c '%a' /tmp/t0106_h2_test
755
$ .venv/bin/python tools/inbr_draft_index.py --worker-drafts .cadgpt/inbr/worker-drafts \
    --ledger .../ledger.json --out /tmp/t0106_h2_test/draft-index.json
$ stat -c '%a' /tmp/t0106_h2_test      # pre-existing dir: unchanged
755
$ stat -c '%a' /tmp/t0106_h2_test/draft-index.json   # the file itself: still 0600
600
$ rm -rf /tmp/t0106_h2_fresh
$ .venv/bin/python tools/inbr_draft_index.py --worker-drafts .cadgpt/inbr/worker-drafts \
    --ledger .../ledger.json --out /tmp/t0106_h2_fresh/draft-index.json
$ stat -c '%a' /tmp/t0106_h2_fresh     # freshly created by this run: tightened
700
```

**H1 (mtime tie-break, documented as a known limitation, not fixed)** — review reproduced that
the mtime-based generation proxy flips 13/50 multi-candidate chunks' outcome under
`cp`/`rsync`/rebuild, since mtimes are not guaranteed to survive a copy of the tree. Per the
coordinator's explicit branching ("fix if cheap, otherwise state as a known limitation"): a
robust replacement needs a generation signal derived from something other than filesystem
metadata across ~70 worker directories whose names do not themselves encode order (the same
problem the docstring already argues against a hand-maintained table for) — not a cheap fix,
and rebuilding it under this review pass risked introducing exactly the kind of new defect this
round is fixing. **Known limitation, stated plainly:** the determinism this tool guarantees is
scoped to *one unmodified checkout, mtimes untouched between runs* — proven below by running
twice against the live tree — not to byte-for-byte reproducibility after a `cp`/`rsync`/rebuild
of `worker-drafts/`, which can change which survivor wins a multi-candidate tie. This is not
claimed as unconditional determinism anywhere in the corrected text below.

**`make verify`:**
- `contracts` (`lint-imports --no-cache`): **PASS** — `Contracts: 7 kept, 0 broken.`
  (`tools/` is not a `root_package`, unaffected either way.)
- `test` (`pytest -m "not postgres"`, run directly, twice — full run, not just this task's
  files): **PASS** both times, exit code 0, no `FAILED`/`ERROR` line and no "short test
  summary" section (pytest prints that section only when a test failed or errored — its
  absence plus exit 0 is the definitive signal, not just an eyeballed dot count), only
  pre-existing collection warnings:
  ```
  $ .venv/bin/python -m pytest -m "not postgres" -q > /tmp/pytest_full.log 2>&1; echo EXIT:$?
  ...
  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
  EXIT:0
  $ grep -aE "FAILED|ERROR |short test summary" /tmp/pytest_full.log
  (no matches)
  ```
- `lint` (`ruff check .` / `ruff format --check .`) and `types` (`mypy` over
  `packages/engine/src packages/regulations/src services/api/cadgpt`): **FAIL, pre-existing
  and out of scope.** Verified by `git status --porcelain` on every failing file *before*
  touching anything: `build_chunk301.py`, `tools/generate_rule_drafts_b.py`, and
  `services/api/cadgpt/apps/inbr/management/commands/rule_extraction_import.py` are clean
  (committed at HEAD, untouched by this task or any other) — pre-existing debt from the
  `feat/inbr-regulations-pipeline` merges, unrelated to T-0106. The rest of the 43 mypy
  errors / 55 ruff errors are in the `rule_compiler.py`/`ids_compiler.py`/`rule_ir.py`/
  `cli.py`/`provisional_rule.py`/etc. cluster, which `git status` shows mid-edit by a
  concurrent task at the time of this run (`M`/`D` on exactly that cluster) — explicitly
  out of scope per this task's brief ("Do not touch `rule_compiler.py` or `ids_compiler.py`
  — another task owns those concurrently"). `tools/inbr_draft_index.py` itself is clean:
  `ruff check tools/inbr_draft_index.py` → `All checks passed!`;
  `ruff format --check tools/inbr_draft_index.py` → `1 file already formatted`. It is not
  type-checked at all — `make types` runs `mypy packages/engine/src packages/regulations/src
  services/api/cadgpt`, which does not include `tools/`, matching T-0066.

**Real path**, against the real 900-file tree, nothing under `worker-drafts/` modified,
re-run after the C1 fix:
```
$ .venv/bin/python tools/inbr_draft_index.py \
    --worker-drafts .cadgpt/inbr/worker-drafts \
    --ledger .cadgpt/inbr/extraction/revision-2026-09-09-paddle/ledger.json \
    --out .cadgpt/inbr/draft-index.json
chunks_resolved=489 chunks_unresolved=179 (sum=668, expected 668)
```
Chunk 42 is still unresolved for the same reason as before (its only candidate has
`"items": []`). Full `index["summary"]`:
```json
{
  "chunks_total": 668,
  "chunks_resolved": 489,
  "chunks_unresolved": 179,
  "chunks_with_multiple_candidates": 209,
  "files_considered": 900,
  "files_chosen": 489,
  "files_rejected_parse_error": 2,
  "files_rejected_templated": 251,
  "files_rejected_record_id_mismatch": 123,
  "files_rejected_superseded": 35
}
```
`2 + 251 + 123 + 35 + 489 = 900 = files_considered`, `489 + 179 = 668 = chunks_total`.
**This is a larger correction than the ~150 estimated** — `files_rejected_templated` jumped
by `201` (50 → 251) and `chunks_unresolved` by `178` (1 → 179), not ~150. That's because the
generalized detector didn't just catch `rule-worker-c`'s variant; it caught **newly-discovered
stub sources in other directories too** (below) — direct evidence the literal three/four-
sentence approach could never have been complete, which is the whole reason C1 asked for
distribution-based detection instead of another hardcoded string.

**Newly-discovered stub sources beyond `rule-worker-a/b/c`:** of the 251 templated rejections,
199 are under `rule-worker-a/`, `rule-worker-b/`, or `rule-worker-c/` (up from 49/50 under the
old literal check) and **52 are not** — e.g. `luna-resume-4`, `luna-rule-resume-24` — using a
*different* canned sentence again (inspected directly: chunk 322's `luna-resume-12` candidate,
previously recorded "real" with `stub_check.templated_items: 0`, turns out to have all 9 items
carrying one identical "safe IDS mapping not possible" refusal sentence, a fifth variant this
task did not know about until the corrected detector found it). `rule-worker-a/b/c` chosen
count is now **0** (down from 150) — every chunk that depended on those three directories is
now genuinely `unresolved`, matching the task's "must become `unresolved`, not silently
re-stubbed" requirement.

**Honest caveat on the new detector, found while re-running:** distribution collapse is a
proxy, not a certainty — a chunk whose source pages are genuinely, repeatedly blank produces
the same true (not invented) finding on every record and can also collapse to one string. I
checked: of the 251 templated rejections, cross-referencing each against its transcript's
average `text_fa` length, only **3** correspond to chunks whose transcript text is near-empty
(avg < 100 chars/record) — e.g. chunk 26, `rule-worker-3`, whose 10 records are confirmed (by
reading the transcript directly) to be literally blank pages carrying only a page number, so
"page only has a page number/blank spaces" repeated ten times is true, not templated. The
other 248 (98.8%) correspond to chunks with substantial real transcript content (confirmed:
chunk 350's pages carry 761–1,594 characters of real lighting-code text, yet all got the
identical `rule-worker-c` refusal) — genuine stubs. This is not fixed further per the
coordinator's stop instruction; it is a real, small precision cost (≈3 chunks) of trading
literal-match recall for distribution-based recall, and it fails in the safe direction for
this product's invariants (`unresolved`, never a silently-wrong `PASS`-equivalent selection) —
noted here as an observation, not silently smoothed over.

**Named multi-draft example — chunk 76** (chosen file genuinely diverse across all 10 items;
one rejected candidate is a newly-caught stub, another rejected for record ID mismatch),
pasted verbatim from the regenerated index:
```json
{
  "chunk": 76,
  "chosen": {
    "path": ".cadgpt/inbr/worker-drafts/luna-rule-resume-13/chunk-76-extraction.json",
    "sha256": "f801f788d8989e78320b0fcbc12b8ee9b0807b6a4a2f1de2757d1bc08b36937f",
    "worker_id": "luna-rule-resume-13",
    "mtime": 1789415207.0,
    "collapse_check": {"total_items": 10, "items_with_reason": 10, "distinct_reasons": 10,
                        "verdict": "not_templated"}
  },
  "rejected": [
    {"path": ".../luna-rule-resume-24/chunk-76-extraction.json", "reason": "templated",
     "detail": "10/10 items carry a reason/unsupported_reason and collapse to 1 distinct string"},
    {"path": ".../rule-worker-batch2/chunk-076-extraction.json", "reason": "record_id_mismatch",
     "detail": "record_id sets differ: 10 in transcript but not items (e.g. ['page-19', ...]), ..."}
  ]
}
```
`luna-rule-resume-13`'s file won because all 10 of its items carry a genuinely distinct reason
(`distinct_reasons: 10` of `10`) — real per-record analysis, not a stamped sentence.

**Chunk 322 (the previous example) is now `unresolved`, correctly:** all 4 of its candidates
fail — 2 are `templated` (one under the original hardcoded set, one under the newly-caught
"safe IDS mapping not possible" variant), 1 is `parse_error` (invalid JSON), 1 is
`record_id_mismatch`. Previously this chunk showed a false "real" chosen file; it is now
honestly `unresolved`, which is the C1 fix working as intended.

**Determinism** — two independent runs into two output paths, same tree, same run, after the
C1/H2 fix (scope of this guarantee: see **H1** above):
```
$ .venv/bin/python tools/inbr_draft_index.py --worker-drafts .cadgpt/inbr/worker-drafts \
    --ledger .../ledger.json --out .cadgpt/inbr/draft-index-run1.json
$ .venv/bin/python tools/inbr_draft_index.py --worker-drafts .cadgpt/inbr/worker-drafts \
    --ledger .../ledger.json --out .cadgpt/inbr/draft-index-run2.json
$ sha256sum .cadgpt/inbr/draft-index-run1.json .cadgpt/inbr/draft-index-run2.json .cadgpt/inbr/draft-index.json
bf9366f023fc1aa16e072b84c9cdc63c4b858ddb676affe2ff0824c39d4ad353  .cadgpt/inbr/draft-index-run1.json
bf9366f023fc1aa16e072b84c9cdc63c4b858ddb676affe2ff0824c39d4ad353  .cadgpt/inbr/draft-index-run2.json
bf9366f023fc1aa16e072b84c9cdc63c4b858ddb676affe2ff0824c39d4ad353  .cadgpt/inbr/draft-index.json
$ diff .cadgpt/inbr/draft-index-run1.json .cadgpt/inbr/draft-index-run2.json && echo IDENTICAL
IDENTICAL
```
(Both scratch copies deleted after the check; `.cadgpt/inbr/draft-index.json` — the one named
in "How to prove it ran" — carries the same sha256, confirmed above.)

**Cross-check — no `rule-worker-a/b/c` file chosen without a recorded reason it passed the
templated check (corrected):** every chosen entry's `chosen.collapse_check` field states
`{total_items, items_with_reason, distinct_reasons, verdict}` directly in the index, checked
independently (not the detector grading its own pass/fail label — C2's fix): **0 chunks** now
choose a file under `rule-worker-a/`, `rule-worker-b/`, or `rule-worker-c/` (down from the
previously-reported, now-known-wrong 150). The cross-check the task asked for is trivially
satisfied because the set it quantifies over is empty, and that emptiness is itself the
correction C1 required.

**Wiring:** this is a standalone offline tool, not a Django component — there is no
route/task/migration to register, matching its Scope ("A committed tool and a generated
index"; explicitly "does not... import anything into PostgreSQL"). Its entry point is
`tools/inbr_draft_index.py`'s `if __name__ == "__main__": raise SystemExit(main())`, invoked
exactly as shown above with `argparse`-declared `--worker-drafts`/`--ledger`/`--out`, the same
invocation the task's "How to prove it ran" specifies. `.cadgpt/inbr/draft-index.json` is
confirmed git-ignored: `git check-ignore -v` → `.gitignore:23:/.cadgpt/inbr/` →
`.cadgpt/inbr/draft-index.json`, and written mode 0600 under its 0700 parent
(`stat -c '%a %n' .cadgpt/inbr/draft-index.json` → `600`).

**NOT DONE:**
- `make verify`'s `lint` and `types` stages remain red for this branch as a whole, but for
  reasons proven pre-existing/concurrent and outside this task's file scope (see above) — not
  for anything `tools/inbr_draft_index.py` introduces, and not something this task is
  permitted to fix given its explicit "do not touch `rule_compiler.py`/`ids_compiler.py`"
  boundary and the CLAUDE.md rule against unscoped wider changes.
- **H1** (mtime-based generation tie-break) is a stated, not fixed, known limitation: it is
  stable for repeated runs against one unmodified checkout (proven above) but not guaranteed
  stable across a `cp`/`rsync`/rebuild of `worker-drafts/` — review reproduced 13/50
  multi-candidate chunks flipping under that condition. A filesystem-metadata-independent
  generation signal is a separate, non-cheap piece of work (see H1 above for why) and was not
  attempted in this pass per the coordinator's explicit instruction to document rather than
  chase it here.
- The **≈3-chunk false-positive risk** in the corrected templated detector (genuinely blank,
  repeated pages colliding with the same "collapses to ≤1 distinct string" signature real
  stubs produce) is recorded as an observation above, not resolved — resolving it would need
  correlating each candidate's reasons against its transcript's actual text content, which is
  more than this review round asked for.

## Review
