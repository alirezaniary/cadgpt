# CadGPT database backup

This directory contains a PostgreSQL custom-format dump of the local `cadgpt` database.

## Restore on another machine

1. Install PostgreSQL 17 (or a compatible newer version).
2. Create an empty database, for example:

   `createdb -U postgres cadgpt`

3. Restore the dump:

   `pg_restore -U postgres -d cadgpt --no-owner --no-privileges cadgpt-database-2026-09-16.dump`

4. Point the application at it with `DATABASE_URL`, then run the application migrations only if the target database is intentionally being upgraded.

## What is in it

- 43 source-document records and their SHA-256/file metadata.
- 5,892 processed PDF-page records, including native/Paddle/Luna extraction fields and statuses.
- 3,346 rule-candidate records awaiting review.
- Django migration and application metadata required by the schema.

The dump is data, not a complete PostgreSQL server installation. Keep the source PDFs and generated artifacts alongside it: database paths and hashes refer to those materials, and the dump does not embed the original PDF files.

## Important credentials

The development compose configuration uses database `cadgpt`, user `cadgpt`, and password `cadgpt`; change these credentials for any real deployment.
