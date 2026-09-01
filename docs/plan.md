# Plan — reach a working MVP

**The MVP:** a web app where you upload an IFC model and an IDS rule file, and get back a report
of what passes, what fails, and what could not be determined. Rules are data — no building code
is baked in. Iranian code translation is out of scope.

Status of each phase is recorded here as it completes. `docs/decisions.md` holds the reasoning.

---

## Phase 0 — Prove the toolchain — **DONE 2026-09-01**

Nothing in the repository had ever run an IDS against an IFC. Everything downstream assumed it
worked. It does:

| Model | Rules | Time | Result |
|---|---|---|---|
| Duplex 2.3MB (US) | Wooden Windows (NL) | 1.4s | 46 fail — correct, wrong standard for the model |
| Schependomlaan 47MB (NL) | BIM Basis ILS (NL national standard) | 9.9s | 7 pass / 3,623 fail |
| Schependomlaan 47MB | Hand-written "door ≥ 900mm" numeric rule | 5.4s | 92 pass / 113 fail |

Two findings, both recorded in `docs/decisions.md`:

1. **9.9s for 47MB means no job queue is needed.** The MVP evaluates synchronously.
2. **`ifctester` conflates "data missing" with "rule violated".** Of 113 reported door-width
   failures, only 12 doors are too narrow; 101 have no width recorded. Separating those is the
   product's whole value-add.

Real IDS files are freely available — the buildingSMART `IDS` repository ships 12 real-world
examples including national standards, and `TestCases/` holds 346 more covering every facet
type including numeric bounds.

---

## Phase 1 — Reset the repository — **DONE 2026-09-01**

`main` reset to `942b45f`; the nine commits after it discarded. Remaining framework stripped.
Recovery branch: `backup/pre-reset-20260901`. Detail in `docs/decisions.md`.

---

## Phase 2 — The thinnest real web app — **NEXT**

Django, one screen, synchronous. No tenancy, no Celery, no S3, no React.

```
engine/check.py     wraps ifctester: (ifc bytes, ids bytes) -> report
web/                Django project
  reviews/          models.py, views.py, templates/
```

- `engine/check.py` is the only domain code and imports no Django. That boundary is enforced by
  the import contract from day one.
- `Review` model: uploaded IFC, uploaded IDS, status, result JSON, timestamp. Local disk via
  `FileField`, SQLite.
- One page: two file inputs → POST → evaluate → result page.
- Normalize the `ifctester` output into `PASS | FAIL | INDETERMINATE` on the way out, so
  "missing data" never renders as a violation. This is the point of the product, and it belongs
  in `engine/`, not the template.

**Done when:** in a browser, uploading a downloaded IFC and IDS produces a report that
distinguishes violations from unknowns. Plus a test that calls `engine.check` on a small
committed fixture pair and asserts the counts.

## Phase 3 — Hold up under real use

Driven by measurement, not anticipation. Postgres when there is more than one concurrent user.
A worker only if measured evaluation time approaches the request timeout. Docker Compose once
more than one process needs starting. S3 only when deploying somewhere that needs it.

## Phase 4 — Make it a product

Django auth and a `user` FK so people see only their own reviews. Farsi-first RTL presentation.
Report grouped by specification, failing entities listed with GlobalIds, canonical JSON download.

---

## Not building yet

PostgreSQL RLS, transactional outbox, idempotency keys, worker leases, S3 multipart upload
authorization, WebSocket progress with polling recovery, React. Each is a real concern for a
product with paying tenants and wrong for one with no working code. They return when there is
something to protect.
