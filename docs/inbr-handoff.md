# INBR Pipeline Handoff

This file is the durable handoff for the INBR transcription work. A new session must
inspect the repository and generated receipts before doing any work; it must not infer
state from chat history.

## Scope Boundary

The Persian structured transcript stage is complete. The assembled transcript JSON is the permanent
checkpoint for all downstream work: it contains the final Persian text plus the source PDF/document
identity and page numbers produced by the PDF, PaddleOCR, and Luna workflow. The downstream
transcript-to-rule flow is documented in
[INBR Transcript-to-Rule Flow](inbr-transcript-to-rules.md). It covers provisional candidate
  generation, transcript citations, corrections, duplicate handling, deterministic normalization,
  IDS compilation, and publication gates. Downstream stages do not reopen PDFs or rerun OCR.

## Intended Pipeline

1. Keep the acquired source PDFs immutable and authoritative.
2. Inspect each PDF page's native structure first.
3. For a normal text page, preserve native PDF text directly. Do not rasterize it and
   do not send it through OCR.
4. Render only OCR-required pages: image scans, degraded pages, mixed pages, or pages
   explicitly needing visual review.
5. Run PaddleOCR with CUDA (`gpu:0`) only on those rendered OCR pages. Preserve raw
   text, boxes, confidence, model identity, and page identity.
6. Build deterministic bounded contiguous PDF chunks. Each chunk binds its source PDF,
   page range, native evidence, Paddle evidence, prompt hash, and response-schema hash.
7. Run three Luna workers in parallel. Each worker receives a different pending chunk
   and returns one Persian structured transcript. There are no sequential Luna passes.
8. Record chunk state and output paths in the durable ledger. A restart dispatches only
   chunks without a valid completed result.
9. Keep chunks reassemblable: `chunk_order`, document order, page ranges, and ordered
   page IDs are part of every job/result. A deterministic assembler must be able to
   rebuild the book from completed Persian structured JSONs, accepting only declared
   overlap pages and never silently reordering or filling gaps.

The current Codex session is the coordinator. Do not create a separate coordinator
agent. The worker model is `gpt-5.6-luna`; the coordinator may use the configured master
identity only as orchestration metadata, not as an extra processing stage.

## Verified Run State

- Acquisition receipt: `.cadgpt/inbr/acquisition/revision-2026-09-06/acquisition.json`
- Acquisition: 43 documents and 5,892 source pages; source PDFs are still present.
- The corrected run is `.cadgpt/inbr/transcription/revision-2026-09-09-paddle`.
- The page-probe implementation now extracts native PDF structure first and omits
  `render.png` for native-only pages. Rendering is limited to OCR or visual-review routes.
- Page probing and Paddle transcription are complete, with zero failed pages.
  The transcription manifest is
  `manifests/transcription/eefa90439f34920f139f6a1cedb6f96de49613549a9f4937857b948fccd680dc.json`.
  Its successful validation receipt is
  `checks/transcription/c8a8c412b572c31510cb1dcb11c9d470ffeb49ddd60355ff6232ea973c2ebd60.json`.
- The active queue and ledger are `jobs.json` and `ledger.json` under
  `.cadgpt/inbr/extraction/revision-2026-09-09-paddle`. There are 668 chunks.
  Read the live ledger and agent handles for progress; do not infer it from this file.
- Interrupted probe packages are preserved outside the active root in
  `.cadgpt/inbr/transcription/quarantine-revision-2026-09-09`.
  An earlier rejected queue is preserved in
  `.cadgpt/inbr/extraction/rejected-queue-2026-09-09-missing-blank-pages`.
  Neither is an active input. The corrected queue includes blank pages and explicit
  `overlap_page_ids`.
- Use a fresh Luna context for each new chunk. See `docs/inbr-luna-worker.md` for the
  worker contract. Do not create a separate coordinator agent or use old helper scripts.
- The CUDA environment is `tools/paddleocr/.venv`; the default project environment
  does not have Paddle. Do not rerun completed probing or OCR stages.

## Required Startup Procedure

1. Run `./tools/inbr_pipeline_status.py --json` and inspect its machine-readable
   state/receipts.
2. Confirm source acquisition hashes and process state.
3. Do not reuse the old all-pages-rendered manifest for the corrected run.
4. Reuse attested completed probe/transcription receipts. If rebuilding is necessary,
   run the corrected native-first probe and Paddle only for OCR-required pages.
5. Reuse the active queue and ledger; generate them only when absent.
6. Call `get-next` to inspect pending chunks, then `mark-started` to lease at most
   three chunks to distinct workers. Do not edit queue or ledger JSON directly.
7. Each worker writes its response through `mark-finished`; that command validates and
   stores the response and Persian structured-transcript result before marking the
   chunk complete. Use `mark-failed` or `reclaim` for recovery.
8. Re-run status after every worker completion or interruption.
9. Assemble only after every required chunk is complete; verify source identity and
   page continuity before writing the assembled Persian transcript.

`assemble-transcripts --audit-only` checks completed results and reports unique page
and document coverage without writing assembled books. Supply `--jobs`, `--ledger`,
`--acquisition`, `--acquisition-root`, and the active `--output-root`. Omit
`--audit-only` only after every required chunk is complete. The assembler refuses
incomplete coverage and retains differing readings on declared overlaps explicitly.

## Invariants

- Never mutate or replace an acquired PDF.
- Never overwrite an existing content-addressed result with different bytes.
- Every result must identify exactly one source PDF and inclusive page range.
- A completed chunk is complete only when its response and Persian structured result
  both exist and match the ledger hashes.
- Completion order must not affect chunk assignment or result paths.
- Completed chunks must concatenate in canonical document/page order to reconstruct
  the source book; gaps, unexpected duplicates, and source drift are blocking errors.
- Generated artifacts stay outside Git; source code and this handoff remain reviewable.
