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
  --tessdata /path/to/tessdata-best \
  --workers 8 \
  --page-timeout 300

page_probe_manifest=<exact-path-printed-by-page-probe>

uv run cadgpt-regulations transcribe \
  --probe "$page_probe_manifest" \
  --root "$transcription_root" \
  --tessdata /path/to/tessdata-best \
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

### 3. Build and check source structure

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

### 4. Prepare, ingest, and inspect blind semantic work

`extract-jobs` only writes an immutable job manifest; it does not call an inference service. An
external coordinator must store raw responses under `extraction_root` and submit each one through
`extract-ingest` or `validator-ingest`.

Each structured job carries both the original T-0100 transcription bundle hash and the exact
T-0101 structural-bundle hash/path. A worker response must preserve both identities; candidates
must cite at least one structural source node, and formula/table references are checked against the
attested structural bundle before ingestion.

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

### 5. Publish only accepted structured semantic evidence

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
