# INBR corpus operations

The INBR pipeline's real data belongs in this checkout's private, ignored workspace:

```text
.cadgpt/inbr/
  acquisition/
  transcription/
  structure/
  extraction/
  validation/
  publication/
```

Do not use `/tmp` for a real corpus run. `/tmp` is suitable for tests and throwaway experiments,
but its contents can disappear at reboot. The workspace is ignored by Git; it contains official
PDFs, renders, OCR, raw model responses, receipts, deferred-review data, and publications that
must not be committed.

## Initialize it

Run this once from the repository root:

```sh
make inbr-workspace
```

This invokes `cadgpt-regulations workspace --root .cadgpt/inbr`. Missing directories are
created as current-user-owned `0700` real directories. Existing directories must be owned by the
current user and must not be group/world writable; symlinks and symlinked ancestors are rejected.
The command applies the existing corpus storage contract rather than silently changing permissions.

The pipeline still requires explicit roots at every stage. That is deliberate: a receipt records
which immutable artifact tree it came from, and there is no hidden fallback root.

## Run and resume a cohort

Set stable shell variables once per shell:

```sh
inbr_root=$PWD/.cadgpt/inbr
cohort_id=revision-2026-09-06
acquisition_root=$inbr_root/acquisition/$cohort_id
transcription_root=$inbr_root/transcription/$cohort_id
structure_root=$inbr_root/structure
extraction_root=$inbr_root/extraction
validation_root=$inbr_root/validation
publication_root=$inbr_root/publication
catalog=packages/regulations/src/cadgpt_regulations/data/inbr_catalog.json
```

### 1. Acquire and attest the pinned official cohort

Create the cohort-specific output roots once. The workspace initializer intentionally creates only
the stable stage roots; each cohort root remains caller-created so the acquisition trust boundary can
attest its ownership and permissions.

```sh
mkdir -m 700 "$acquisition_root"
mkdir -m 700 "$transcription_root"

uv run cadgpt-regulations acquire \
  --catalog "$catalog" \
  --output-root "$acquisition_root"

uv run cadgpt-regulations acquisition-check \
  "$acquisition_root/acquisition.json" \
  --root "$acquisition_root" \
  --catalog "$catalog"
```

The acquisition receipt is the stable entry point for downstream stages. `cohort_id` must identify
the exact curated snapshot: use a new, never-before-used ID when the catalog changes. Do not rerun a
revised catalog against a previous cohort root; that preserves its receipt, raw official responses,
and immutable artifacts as historical evidence. Rerunning `acquire` with the same catalog and root
re-attests existing immutable artifacts and reuses identical bytes without changing their mtimes; it
does not overwrite differing evidence.

### 2. Probe and transcribe pages

`page-probe` and `transcribe` print content-addressed manifest paths. Copy the printed paths
exactly into your run log or shell variables; do not infer a “latest” manifest by directory
ordering.

```sh
uv run cadgpt-regulations page-probe \
  --acquisition "$acquisition_root/acquisition.json" \
  --root "$acquisition_root" \
  --output-root "$transcription_root" \
  --render-dpi 400 \
  --paddle-device gpu:0 \
  --workers 8 \
  --page-timeout 300

page_probe_manifest=<exact-path-printed-by-page-probe>

uv run cadgpt-regulations transcribe \
  --probe "$page_probe_manifest" \
  --root "$transcription_root" \
  --paddle-device gpu:0 \
  --workers 8 \
  --ocr-timeout 300

transcription_manifest=<exact-path-printed-by-transcribe>

uv run cadgpt-regulations transcription-check \
  "$transcription_manifest" \
  --root "$transcription_root" \
  --acquisition-root "$acquisition_root" \
  --catalog "$catalog"
```

The immutable packages, manifests, checks, and bundles remain below `transcription_root`.

The probe extracts native PDF structure first. It renders only pages that need visual evidence
or OCR: textless pages, mixed pages, suspect native pages, and scan/photo pages. It does not
replace the PDF or native text. PaddleOCR runs only for `ocr` and `native_plus_ocr` routes;
clean native pages keep their native PDF text as the authoritative source view and have no
render artifact.

### 3. Refine into a Persian structured transcript

Queue one independent Luna chunk for each bounded transcription bundle. Each chunk binds the original
PDF hash and page range, page-render hashes, native-text hashes, Paddle result hashes, and the
exact prompt/response-schema hashes. The coordinator leases chunks in stable order to up to three
parallel workers. Each worker returns one Persian structured transcript; no English rules, IDS, or
publication stage is part of this flow.

```sh
transcript_root=$inbr_root/transcription/$cohort_id
transcript_output=$inbr_root/extraction/$cohort_id
mkdir -m 700 -p "$transcript_output"

uv run cadgpt-regulations transcript-jobs \
  --transcription "$transcription_manifest" \
  --transcription-root "$transcript_root" \
  --acquisition-root "$acquisition_root" \
  --output-root "$transcript_output" \
  --model gpt-5.6-luna

jobs=$transcript_output/jobs.json
```

Initialize and lease the resumable ledger. The lease command is safe for concurrent workers and
always selects the lowest pending `chunk_order` first:

```sh
uv run cadgpt-regulations transcript-jobs \
  --jobs "$jobs" \
  --output-root "$transcript_output"

uv run cadgpt-regulations mark-started \
  --jobs "$jobs" \
  --output-root "$transcript_output" \
  --worker-id luna-1 \
  --max-workers 1
```

Workers can inspect pending chunks with `get-next`, then submit one response with its lease token
through `mark-finished`. The ledger records
the worker, attempts, response hash/path, and final Persian structured-transcript hash/path. A
failed work is recorded with `mark-failed` and made pending again with `mark-started`; an
interrupted lease can be returned with `reclaim`. English rule projection, IDS compilation, web
validation, and publication are intentionally outside this stage.

### 4. Build and check source structure

```sh
uv run cadgpt-regulations structure \
  --transcription "$transcription_manifest" \
  --root "$transcription_root" \
  --output-root "$structure_root"

structure_manifest=<exact-path-printed-by-structure>

uv run cadgpt-regulations structure-check \
  "$structure_manifest" \
  --root "$structure_root" \
  --transcription "$transcription_manifest" \
  --transcription-root "$transcription_root"
```

### 5. Prepare, ingest, and inspect blind semantic work

This section documents the earlier T-0028 semantic-evidence importer. It is not the downstream
transcript-to-rule path. After the transcript checkpoint, use `provisional-batch` below; do not
run this importer again for the completed corpus.

`extract-jobs` only writes an immutable job manifest; it does not call an inference service. An
external coordinator must store raw responses under `extraction_root` and submit each one through
`extract-ingest` or `validator-ingest`.

These legacy jobs carry T-0027 structure identities and are retained only for historical reruns of
that upstream stage.

```sh
uv run cadgpt-regulations extract-jobs \
  --transcription "$transcription_manifest" \
  --root "$transcription_root" \
  --structure "$structure_manifest" \
  --structure-root "$structure_root" \
  --output-root "$extraction_root"

jobs=$extraction_root/jobs.json

uv run cadgpt-regulations extract-ingest \
  --jobs "$jobs" \
  --job-id <job-id> \
  --response /private/path/to/response.json \
  --transcription-root "$transcription_root" \
  --structure-root "$structure_root" \
  --output-root "$extraction_root"

uv run cadgpt-regulations validator-ingest \
  --jobs "$jobs" \
  --bundle-id <bundle-id> \
  --response /private/path/to/validator-response.json \
  --transcription-root "$transcription_root" \
  --structure-root "$structure_root" \
  --output-root "$extraction_root"

uv run cadgpt-regulations extraction-status \
  --jobs "$jobs" \
  --output-root "$extraction_root"
```

### 6. Publish only accepted structured semantic evidence

This is also a legacy T-0030 command for rebuilding the earlier semantic-evidence publication.
It is not required for the current transcript-to-rule run and should not be used as a reason to
reopen the PDF. The current downstream entry point is the transcript JSON plus
`provisional-batch`.

The current implementation provides `semantic-publish` and `semantic-publish-check`. It remains
a semantic-evidence boundary—not IDS compilation and not a compliance verdict.

```sh
uv run cadgpt-regulations semantic-publish \
  --catalog "$catalog" \
  --acquisition "$acquisition_root/acquisition.json" \
  --acquisition-root "$acquisition_root" \
  --jobs "$jobs" \
  --structure "$structure_manifest" \
  --extraction-root "$extraction_root" \
  --structure-root "$structure_root" \
  --output-root "$publication_root"

semantic_publication=<exact-path-printed-by-semantic-publish>
semantic_publication_root=$(dirname "$semantic_publication")

uv run cadgpt-regulations semantic-publish-check \
  "$semantic_publication" \
  --root "$semantic_publication_root"
```

These commands re-attest the structured evidence files, but they do not establish that the
publication is complete. Read the printed `complete` value and the manifest's pending and validation
counts; any `complete: false`, pending bundle, or bundle needing validation remains unfinished and
must not advance an automated release. The planned official-web validation and final corpus-release
stages have their own task contracts; do not invent paths or claim their commands are available until
those tasks land.

### 7. Keep OCR-tolerant rule candidates

OCR damage does not need to stop rule generation. The completed Luna JSON is the source
checkpoint. Its PDF/document name, page number, transcript record, and text hash are enough
to cite a rule; no source-span re-anchoring or second OCR pass is required. Store the complete
Luna JSON as an immutable transcript revision, then create a page/table-level sandbox candidate
with `provisional-rule`:

```sh
uv run cadgpt-regulations provisional-rule \
  --transcript path/to/assembled-transcript.json \
  --rule path/to/rule-payload.json \
  --output-root "$inbr_root/candidates/$cohort_id" \
  --revision luna-<chunk-or-table-revision> \
  --edition 'ویرایش ۱۴۰۱' \
  --table-index 0 \
  --state needs_review
```

This writes a content-addressed transcript revision, including the full Luna payload and hash,
and a candidate rule. Candidates may be used for sandbox analysis and prioritization, but are
never official engine releases. A correction creates a new revision with `supersedes`; it never
mutates the original Luna result. Transcript revision/hash verification, review, and deterministic
compilation promote a candidate into an official IDS release.

For a structured transcript with several sections, tables, or clauses, use the batch boundary.
The extraction response is produced by the replaceable rule-extraction worker and must contain
one item for each source `record_id`, with either a rule or an explicit `no_assertion` reason:

```sh
uv run cadgpt-regulations provisional-batch \
  --transcript path/to/assembled-transcript.json \
  --extraction path/to/rule-extraction.json \
  --output-root "$inbr_root/candidates/$cohort_id" \
  --revision luna-<revision> \
  --edition 'ویرایش ۱۴۰۱'
```

The batch writes one immutable transcript revision per source record, candidate files, and a
content-addressed batch manifest. Missing records are counted as `unprocessed`; records with no
machine-actionable rule are retained as `no_assertion`. Repeated semantic proposals are grouped
by fingerprint while every candidate and citation remains available for review. If two record
types reuse a `record_id`, the extraction item uses the qualified key `tables:<record_id>` (or
the corresponding source collection) so the mapping remains unambiguous.

### 8. Import the transcript projection into Django/PostgreSQL

The assembled JSON remains the immutable source of truth. Django stores a queryable projection:
one `pdf_document` row per PDF and one `pdf_page` row per physical page, including blank pages.
Apply the normal Django schema migration, then run the explicit idempotent import command:

```sh
cd services/api
uv run --project ../.. python manage.py migrate
uv run --project ../.. python manage.py import_inbr_projection \
  --transcription-manifest ../../.cadgpt/inbr/transcription/revision-2026-09-09-paddle/manifests/transcription/eefa90439f34920f139f6a1cedb6f96de49613549a9f4937857b948fccd680dc.json \
  --transcription-root ../../.cadgpt/inbr/transcription/revision-2026-09-09-paddle \
  --assembled-manifest ../../.cadgpt/inbr/extraction/revision-2026-09-09-paddle/assembled/manifests/699e7122e9ea8e073bfb2dbd03a020b05eeeef17211566cbb636808926f2c1a6.json \
  --assembled-root ../../.cadgpt/inbr/extraction/revision-2026-09-09-paddle \
  --extraction-root ../../.cadgpt/inbr/extraction/revision-2026-09-09-paddle
```

The command verifies source identities, page continuity, completed Luna responses, and hashes
before writing. Re-running it updates the same natural-key rows without duplicating data. Use
`--dry-run` to validate the complete cohort without writing to PostgreSQL.

## Restart and interruption behavior

Restarting the machine or shell does not alter `.cadgpt/inbr`. To resume, reset the shell
variables above and rerun the same stage with exactly the same root and receipt/manifest identity.
The existing storage contract:

- retains and re-attests immutable matching artifacts;
- reuses them without changing mtimes;
- rejects a different file where an immutable file already exists;
- recovers only recognized, owned interrupted writes; and
- fails closed on unexpected, unsafe, unaccounted, missing, or tampered paths.

The historical task evidence uses `/tmp/cadgpt-inbr-*` directories. Those paths document prior
runs; they are not valid durable-run instructions. If a reboot removed those directories, their
artifacts cannot be recovered. Start again at acquisition in the durable workspace and retain the
printed content-addressed receipt/manifest paths for every downstream stage.
