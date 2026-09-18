# T-0111 — Re-import the projection; two thirds of the current rows came from stubs

**Phase:** Regulation corpus 8 — source-cited rule codification   **Status:** open
**Touches invariants:** tenancy, never assert compliance we did not establish

## Why

A PostgreSQL projection of the corpus already exists, in the `inbr-dump-pg` container restored
from `cadgpt-database-2026-09-16.dump`. Queried on 2026-09-19 it holds **43 documents, 5,892
pages, 3,346 rule candidates** — the page projection is complete and correct. The candidates are
not:

```sql
select count(*) from rule_candidate
 where extraction_file_uri like '%rule-worker-a%'
    or extraction_file_uri like '%rule-worker-b%'
    or extraction_file_uri like '%rule-worker-c%';
--> 2204
```

**2,204 of 3,346 rule candidates (66%) were imported from the three templated stub sources** —
the ones `docs/decisions.md` (2026-09-18) established never read the text at all. This was the
cross-check deferred in `docs/inbr-haiku-remediation-runbook.md` "until the 190 chunks are
filled". They are filled; this is the answer.

Two further facts, both verified the same day:

- The deployed API image predates the merge. `manage.py showmigrations inbr` against the running
  `cadgpt-api-1` returns **"No installed app with label 'inbr'"**, even though
  `cadgpt.apps.inbr` is in `LOCAL_APPS` at `services/api/cadgpt/config/settings/base.py:56`. The
  Django projection has never run in the real stack — only in the side container.
- The Django app and `packages/regulations/sql/rule_projection.sql` are **the same schema, two
  views**: identical `db_table` names (`pdf_document`, `pdf_page`, `rule_candidate`), identical
  index names (`pdf_page_document_page_idx`, `pdf_page_luna_hash_idx`,
  `rule_candidate_fingerprint_idx`), identical column sets. Django's `0001_initial` owns the
  application database; the SQL file is the standalone rebuild script `rule_projection.py`
  mirrors. There is nothing to reconcile — but no test asserts they stay in step, and they will
  drift the first time either is edited alone.

This is last because **it gates nothing**. The compilers read files, not rows; T-0105 through
T-0110 never touch the database. The projection is a query convenience — which is exactly why
stale, two-thirds-templated rows sitting in a container labelled as the corpus is a hazard worth
closing rather than a blocker worth rushing.

## Scope

- **Re-import all 43 documents from T-0106's authoritative index** into the real application
  database via `import_inbr_projection` and `import_inbr_rule_extraction`, replacing the
  templated candidate rows. The import must be idempotent — `CLAUDE.md` requires it of every
  background task and the same reasoning applies to a re-runnable command.
- **Rebuild the API image** so `cadgpt.apps.inbr` is actually present, and show the migration at
  head in the running container. A management command that cannot be invoked where it runs is
  not wired.
- **A drift test** asserting the Django migration state and `sql/rule_projection.sql` describe
  the same tables, columns and indexes. `tests/test_rule_projection_sql.py` already parses the
  SQL; extend it rather than adding a parallel mechanism. Note that
  `packages/regulations` may not import Django (import-linter contract "Regulation corpus core
  has no service or framework dependencies"), so the test that knows about both belongs on the
  `services/api` side.
- **Record the tenancy position explicitly.** `pdf_document`, `pdf_page` and `rule_candidate`
  carry no `tenant` column. That is correct — the INBR corpus is shared reference data, not
  tenant-owned — but `CLAUDE.md`'s tenancy invariant says every tenant-owned table carries
  `tenant` and every read goes through `for_tenant`. State in the task evidence that these
  tables are deliberately tenant-neutral and that no viewset exposes them, so the structural
  test's silence is a fact rather than a gap. If a viewset is ever added, it inherits the scoped
  base class like everything else.
- **Retire the side container.** Once the real database holds the corrected import, the
  `inbr-dump-pg` container and its 66%-templated rows must not remain as an unlabelled
  alternative source of truth.

**Does not change:** the schema. This task fixes what is *in* the tables, proves the path runs
where it is supposed to run, and stops the two definitions drifting.

## How to prove it ran

`make verify`, then the real path against the real application database, not the side container:

```sh
docker compose -f deploy/compose.yaml build api
docker compose -f deploy/compose.yaml exec -T api python manage.py showmigrations inbr
docker compose -f deploy/compose.yaml exec -T api python manage.py migrate inbr
docker compose -f deploy/compose.yaml exec -T api python manage.py import_inbr_rule_extraction \
  --transcript <path> --extraction <chosen draft from the index> --document-key <key>
```

The evidence must paste: `showmigrations inbr` showing `[X] 0001_initial` in the running
container (it currently errors with "No installed app with label 'inbr'", so this line is the
wiring proof); the import summary for all 43 documents; and these counts from the **application**
database, not `inbr-dump-pg`:

```sql
select count(*) from pdf_document;   -- expect 43
select count(*) from pdf_page;       -- expect 5892
select count(*) from rule_candidate;
select count(*) from rule_candidate
 where extraction_file_uri like '%rule-worker-a%'
    or extraction_file_uri like '%rule-worker-b%'
    or extraction_file_uri like '%rule-worker-c%';  -- must be 0
```

Then a second run of the same import showing unchanged counts (idempotence), and the drift test
failing when a column is removed from the SQL file and passing when it is restored.

## Evidence

<!-- the builder writes this -->

## Review
