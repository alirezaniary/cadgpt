# INBR Rule-Extraction Progress

Updated: 2026-09-16

## Verified State

- Upstream acquisition, transcription, queue, ledger, and assembled transcript stages remain complete.
- The active transcript ledger contains 668 chunks; it reports 668 completed, 0 failed, 0 leased, and 0 pending.
- Durable rule-extraction drafts now cover all 668 chunks.
- Full audit result: 668/668 drafts pass `provisional-extraction-1.0.0` validation and exactly cover the authoritative structured-transcript record IDs for their chunks.
- Drafts preserve source record IDs, Persian evidence, page bindings, and review flags; uncertain formulas, tables, and OCR-dependent material remain explicitly flagged.

## Coordinator Audit

For each draft, the coordinator verifies that the file exists and parses as JSON, passes the provisional schema, and has a record-ID set equal to the authoritative `structured_transcript.sections` set for the same chunk. Worker reports additionally verify source/page/evidence bindings, restricted file permissions, and durable filesystem presence.

Existing drafts were preserved. Queue, ledger, acquisition, transcription, and assembled transcript files were not modified during downstream extraction coordination.

## Worker History

Fresh Luna workers were assigned distinct chunks, monitored to completion, and immediately reassigned. The final tail (chunks 277-282) was completed; chunk 278 required a corrected draft because an earlier schema-valid draft used mismatched record IDs.

## Outstanding Work

- Django/PostgreSQL import has not been completed. The importer must still be run with migrations, `--dry-run`, real transactional imports, and idempotency/candidate-count verification once the configured database connection is available.
- No database write is claimed by this document.

## Resume Point

Before database work, rerun the pipeline status command and verify the 668/668 extraction audit. Then configure `DJANGO_SECRET_KEY` and a reachable `DATABASE_URL`, run migrations, perform importer dry-runs, and only then execute real imports.
