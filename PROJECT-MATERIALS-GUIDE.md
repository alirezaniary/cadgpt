# CadGPT project materials guide

This archive preserves the project source, research documents, regulatory PDFs, generated extraction artifacts, tests, and the PostgreSQL backup. It is intended to be understandable and reusable on another machine.

## Main areas

- `packages/engine/`: core engineering/rules engine.
- `packages/regulations/`: document acquisition, page extraction, transcription, semantic validation, rule compilation, schemas, SQL, and tests.
- `services/api/`: Django API, migrations, and database models.
- `services/web/`: frontend application.
- `docs/`: project decisions, task records, research, handoff notes, and operating instructions.
- `docs/inbr/`: original regulation PDFs and related source material.
- `.cadgpt/`: local acquisition, structure, transcript, and pipeline artifacts produced during processing.
- `packages/regulations/artifacts/`: generated page/transcript/semantic outputs and publication artifacts.
- `tools/`: worker, OCR, preview, and pipeline utility scripts.
- `deploy/`: Docker Compose and container definitions.

## What is portable

Source code, documentation, PDFs, JSON/JSONL artifacts, schemas, SQL, tests, and the PostgreSQL custom-format dump are portable. The dump is restored using the instructions in `DATABASE-BACKUP-GUIDE.md`.

## What is intentionally excluded

The archive excludes installed dependency environments (`.venv`, `venv`, `env`, `node_modules`), Python caches, test caches, build output, and Git internals. Recreate dependencies from `pyproject.toml`, lock files, package manifests, and the documented tool requirements.

## Recommended reconstruction order

1. Install Python, Node, PostgreSQL, and Docker.
2. Install dependencies from the project manifests/lock files.
3. Restore PostgreSQL using `DATABASE-BACKUP-GUIDE.md`.
4. Set `DATABASE_URL` and any service credentials for the new machine.
5. Read `docs/inbr-operations.md`, `docs/inbr-handoff.md`, and the task/research documents before running workers.
6. Treat hashes and paths in generated artifacts as provenance references; do not move source PDFs without updating the configured storage paths.

Generated artifacts are evidence and intermediate results, not all production-ready rules. Their statuses and validation fields should be respected when continuing the pipeline.
