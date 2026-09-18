# INBR Luna Worker Contract

Each invocation uses a fresh `gpt-5.6-luna` context and processes exactly one leased
chunk. The root session remains the coordinator. Do not reuse another chunk's
conversation or read previous workers' responses as input.

Read `docs/inbr-handoff.md` first. The coordinator supplies `chunk_order` and
`worker_id`; find that exact leased record and its job in:

- `.cadgpt/inbr/extraction/revision-2026-09-09-paddle/ledger.json`
- `.cadgpt/inbr/extraction/revision-2026-09-09-paddle/jobs.json`

Original PDF paths are relative to `.cadgpt/inbr/acquisition/revision-2026-09-06`.
Evidence paths are relative to `.cadgpt/inbr/transcription/revision-2026-09-09-paddle`.
Use `tools/paddleocr/.venv/bin/cadgpt-regulations` for pipeline commands.

## Evidence Review

Inspect every ordered job page, including blank and declared overlap pages.
Verify the bound source and evidence hashes. Read the native layout/raw text,
normalized reading-order view, and raw Paddle evidence where present. Preserve
native PDF text directly for native-only pages: never rasterize or OCR them.
For OCR routes, visually inspect the existing page renders with the image-viewing
tool and reconcile them with Paddle/native evidence. Reading only OCR strings is
not visual review. Do not run OCR again.

Keep evidence tool output bounded. Before viewing OCR-route pages, run
`.venv/bin/python tools/inbr_worker_previews.py --chunk <chunk_order>` and read the
reported manifest. Inspect its compressed JPEG display copies instead of loading
full-size PNGs; use detailed crops in the private draft directory as needed to
read small text. The helper verifies source render hashes and skips native-only
pages. Avoid accumulating full-size PNGs that can exceed request-size limits.
This changes only the display transport, never source evidence or transcript coverage.
Do not write any derived files in acquisition storage. If using `pdftotext` for a
read-only diagnostic, explicitly pass `-` as its output target (stdout); omitting
the output target creates an unwanted `.txt` beside the PDF and blocks assembly.

Preserve Persian content, digits, clause numbers, headers, footers, tables,
formulas, and cross-references. Correct discrepancies only when supported by the
source evidence. Mark unreadable content and remaining uncertainty explicitly;
do not guess, silently omit content, summarize pages, or invent semantic rules.
The raw native evidence remains authoritative and immutable even where the
structured reading uses normalized Persian presentation forms and reading order.

## Response

Read the complete schema at
`packages/regulations/src/cadgpt_regulations/schemas/structured-transcript.schema.json`
and the prompt/validators in `luna_transcript.py` before writing the response.

The JSON wrapper must contain:

- `schema_version`: `1.0.0`
- `job_id`, `model`, `source_sha256`, `prompt_sha256`, `response_schema_sha256`:
  copied exactly from the leased job; model must be `gpt-5.6-luna`
- `pass`: `structured_transcript`
- `chunk_order`, `catalog_order`, `overlap_page_ids`: copied from the job
- `ordered_page_ids`: all job page IDs in exact order
- `page_transcripts`: one `{page_id, pdf_page, text_fa}` entry for every job page
- `transcript_fa`: the chunk's complete Persian transcript
- `structured_transcript`: an object conforming exactly to the response schema

Each nonempty page must also have a structured `sections` record whose
`source_page_ids` is `[page_id]` and whose `text_fa` exactly matches that page's
`page_transcripts` text. Blank pages remain present in the page list. Preserve
all supported additional structure in the schema's other arrays. Do not produce
English translations/rules, legal decisions, IDS, or downstream extraction.

## Submission

Use `apply_patch` for a unique draft at
`.cadgpt/inbr/worker-drafts/<worker_id>/chunk-<chunk_order>-response.json`.
Make directories private and the draft a regular current-user-owned file without
group/world write permission. Never edit acquired PDFs, input artifacts, source
code, the queue, or the ledger.

Validate the response and submit it through `mark-finished`, supplying the exact
job ID, worker ID, current lease token, response path, jobs path, and output root.
Only the state handler may store results and update the ledger. Preserve failed
drafts; report errors to the coordinator instead of faking completion or retrying
another chunk. Run `./tools/inbr_pipeline_status.py --json` after completion or
interruption, and report the chunk and durable output paths. Do not lease more
chunks or spawn additional agents.
