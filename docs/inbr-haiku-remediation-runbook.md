# INBR rule-extraction remediation: fill the 190 templated chunks

Written 2026-09-18 as a session handoff. A fresh session (or coordinator agent) should be
able to execute this without re-deriving anything below — every fact here was verified by
actually running commands against this checkout, not inferred.

## What this is

The INBR Persian-transcript stage is genuinely complete and validated: 668/668 chunks,
43/43 documents, 5,892/5,892 pages, zero failures (`tools/inbr_pipeline_status.py --json`
reports every stage `ready`). The next stage — reading each chunk's Persian text and
deciding, record by record, whether it states an actionable rule — was run for all 668
chunks, but **three of the sources that produced that output are mechanical scripts that
never actually read the text**: they stamp one hardcoded Persian sentence onto every
record regardless of content. See `docs/inbr-progress.md` for the corrected state and the
detection method (word-for-word reason-text repetition at scale — real analysis produces
distinct wording per record; a script produces the same sentence hundreds of times).

**190 of 668 chunks have only templated output. 477 have genuine analysis. 1 (chunk 42)
hit a JSON parse error in its one available file and needs a manual look.** The exact 190
chunk numbers, reproducibly:

```
310,313,325,326,327,328,329,330,331,332,333,334,335,336,337,338,339,340,341,342,343,344,
345,346,347,348,349,503,504,505,506,507,508,509,510,511,512,513,514,515,516,517,518,519,
520,521,522,523,524,525,526,527,528,529,530,531,532,533,534,535,536,537,538,539,540,541,
542,543,544,545,546,547,548,549,550,551,552,553,554,555,556,557,558,559,560,561,562,563,
564,565,566,567,568,569,570,571,572,573,574,575,576,577,578,579,580,581,582,583,584,585,
586,587,588,589,590,591,592,593,594,595,596,597,598,599,600,601,602,603,604,605,606,607,
608,609,610,611,612,613,614,615,616,617,618,619,620,621,622,623,624,625,626,627,628,629,
630,631,632,633,634,635,636,637,638,639,640,641,642,643,644,645,646,647,648,649,650,651,
652,653,654,655,656,657,658,659,660,661,664,665,666,667
```

Regenerate this list yourself (don't trust it blindly — verify) with the script in
"Verification script" below.

## The job, precisely

For each stub chunk number `N`:

1. **Find its transcript.** `.cadgpt/inbr/extraction/revision-2026-09-09-paddle/ledger.json`
   → `ledger["jobs"][N-1]["structured_transcript_path"]` (0-indexed array, `chunk_order`
   is 1-indexed and matches array position). That path, joined under
   `.cadgpt/inbr/extraction/revision-2026-09-09-paddle/`, is a JSON file with a top-level
   `sections` array — each section has `record_id`, `text_fa`, `source_page_ids`, and a
   few always-null semantic fields (`subject_fa`, `predicate_fa`, etc. — ignore these, they
   were never filled by the transcript stage, that's expected).

2. **Read every section's `text_fa` for real** and, per record, decide:
   - `outcome: "no_assertion"` — the text is a heading, definition, cross-reference,
     informational text, or has no actionable requirement. Give a `reason` specific to
     *that* text (what it actually is), not a template.
   - `outcome: "candidate"` — the text states something a designer must do, may do, may
     not do, or a numeric/table/formula limit. Give a `rule` object:
     `{"rule_key": "<slug specific to this rule>", "title_fa": "...", "statement_fa": "...",
     "implementation_type": "native_ids"|"derived_ids"|"decision_table"|"formula_evaluator"|"unsupported",
     "classification": "<short topic tag>", "unsupported_reason": "<specific to this record,
     omit or leave empty if implementation_type isn't unsupported>", "source_record_id": "<record_id>",
     "source_page_ids": [...from the section...]}`, plus `state: "candidate"` or
     `"needs_review"`, plus `review_flags: [...]`.
   - Every `record_id` in the transcript's `sections` must appear exactly once in the
     output's `items`. Do not invent, merge, or drop a record.

3. **Write the result** conforming exactly to
   `packages/regulations/src/cadgpt_regulations/schemas/provisional-extraction.schema.json`
   (`additionalProperties: false` — extra fields will fail validation), to a **new** path:
   `.cadgpt/inbr/worker-drafts/haiku-pass-1/chunk-<N>-extraction.json`, mode `0600`, parent
   dir mode `0700`.
   Top level: `{"schema_version": "provisional-extraction-1.0.0", "worker_id": "haiku-pass-1-chunk-<N>", "prompt_version": "inbr-rule-extraction-v1", "items": [...]}`.

4. **Validate mechanically before accepting it:**
   ```sh
   uv run --project packages/regulations python -c "
   import json, jsonschema
   schema = json.load(open('packages/regulations/src/cadgpt_regulations/schemas/provisional-extraction.schema.json'))
   draft = json.load(open('.cadgpt/inbr/worker-drafts/haiku-pass-1/chunk-<N>-extraction.json'))
   jsonschema.validate(draft, schema)
   transcript = json.load(open('<the structured_transcript_path from step 1>'))
   want = {s['record_id'] for s in transcript['sections']}
   got = {i['record_id'] for i in draft['items']}
   assert want == got, (want - got, got - want)
   print('ok')
   "
   ```
5. **Reject templating.** Refuse (and redo) any batch where, across all chunks just
   produced, a single `unsupported_reason` or `reason` string appears on more than ~2-3
   records — that is the exact signature that caught the three bad sources last time.
6. **Once accepted, delete the superseded stub file(s)** for that chunk under
   `worker-drafts/rule-worker-a/`, `rule-worker-b/`, or `rule-worker-c/` (whichever had it)
   so re-running the verification script (below) shows the corrected count and progress is
   visible strictly by file presence, not by trusting an agent's report.

## Coordinator/worker split (as requested)

- **Coordinator: one Sonnet agent, medium effort.** Holds the list of 190 chunk numbers,
  dispatches work, runs the schema+coverage validation in step 4 and the anti-templating
  check in step 5 itself (never trust a worker's self-report of either), deletes superseded
  stub files only after its own validation passes, and re-runs the verification script
  after every batch to report real progress.
- **Workers: Haiku agents, 3-5 in flight at a time, one chunk per agent.** Give each
  worker exactly: the chunk number, the transcript file's absolute path (already resolved
  by the coordinator, not the worker), the schema file's path, and the job description in
  "The job, precisely" above. A worker should not need to explore the repo — hand it
  everything it needs so it can't drift into reading unrelated bulk data.
- Do not raise concurrency above 5. Do not let the coordinator accept a worker's output
  without independently re-running steps 4-5 itself.

## Verification script (regenerate the stub-chunk list, or check remaining progress)

```python
import json, os, re, collections

STUB_UNSUPPORTED_REASONS = {
    "متن صفحه برای استخراج ماشینی نیازمند بررسی تخصصی و تعیین دامنه الزام است.",
    "استخراج خودکار نیازمند بازبینی معنایی و تفسیر الزامات فنی است.",
}
STUB_NOASSERT_REASONS = {
    "این رکورد برای استخراج قاعده الزام‌آور روشن، بدون بررسی تخصصی کافی نیست؛ نیازمند بازبینی معنایی است.",
}

base = ".cadgpt/inbr/worker-drafts"
chunk_files = collections.defaultdict(list)
for root, dirs, files in os.walk(base):
    if os.path.basename(root) == "previews":
        dirs[:] = []
        continue
    for fn in files:
        m = re.search(r"chunk-(\d+)-extraction\.json$", fn)
        if m:
            chunk_files[int(m.group(1))].append(os.path.join(root, fn))

def file_verdict(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    items = d.get("items")
    if not isinstance(items, list) or not items:
        return None
    for it in items:
        if not isinstance(it, dict):
            continue
        outcome = it.get("outcome")
        if outcome == "candidate":
            rule = it.get("rule") or {}
            if rule.get("unsupported_reason") not in STUB_UNSUPPORTED_REASONS:
                return False
        elif outcome == "no_assertion":
            if it.get("reason") not in STUB_NOASSERT_REASONS:
                return False
        else:
            return False
    return True

stub, real = [], []
for n in range(1, 669):
    verdicts = [file_verdict(p) for p in chunk_files.get(n, [])]
    if verdicts and all(v is True for v in verdicts):
        stub.append(n)
    elif any(v is False for v in verdicts):
        real.append(n)
print(f"real={len(real)} stub={len(stub)} total_seen={len(chunk_files)}")
print("remaining stub chunks:", stub)
```

## What is explicitly out of scope for this remediation pass

- Do not touch the 27-document PostgreSQL import already restored from
  `cadgpt-database-2026-09-16.dump` (running in the local `inbr-dump-pg` Docker container,
  if still up — check `docker ps`) — that import may itself have picked a stub draft over a
  real one for some chunks; that is a **separate** cross-check, not this remediation's job.
  Re-running the Django import (`import_inbr_rule_extraction`) against the corrected
  `worker-drafts/haiku-pass-1/` output, for all 43 documents fresh, is the right eventual
  fix, but do it after this remediation is complete and reviewed, not concurrently.
- Do not proceed to English glossing, IDS compilation (`rule_compiler.py`,
  `ids_compiler.py`), or publication. `tools/inbr_pipeline_status.py` explicitly names
  these `forbidden_downstream` past the current boundary. Filling the 190 chunks with real
  analysis is the whole scope of this task.
- Do not modify `.gitignore`d `.cadgpt/inbr/` paths outside `worker-drafts/haiku-pass-1/`
  and the specific stub files being superseded.

## Branch / commit state

Work is on branch `feat/inbr-rule-codification`, commit `a4103ea` at time of writing —
a merge of `origin/feat/inbr-regulations-pipeline`'s unmerged tip (which itself was never
merged into `main`; the 2026-09-18 merge to `main` used a stale local copy of that branch).
`packages/regulations` tests pass in full against this commit. `.cadgpt/inbr/` content
(the real corpus data) is git-ignored and lives only in this checkout plus the read-only
backup at `/media/alireza/09210865357/cadgpt-nonrepo-material-2026-09-16.zip` — never write
to that zip.
