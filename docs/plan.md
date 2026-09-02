# Plan — from a checking engine to a product that can carry one

**What this is:** a multi-tenant SaaS where a design office uploads an IFC model and an IDS
rule set and gets back a report of what passes, what fails, and what could not be
determined. Rules are data — no building code is baked in.

Status of each phase is recorded here as it completes. `docs/decisions.md` holds the
reasoning; `prd.md` is the product source of truth.

---

## Phase 0 — Prove the toolchain — **DONE 2026-09-01**

Nothing in the repository had ever run an IDS against an IFC. Everything downstream assumed
it worked. It does:

| Model | Rules | Time | Result |
|---|---|---|---|
| Duplex 2.3MB (US) | Wooden Windows (NL) | 1.4s | 46 fail — correct, wrong standard for the model |
| Schependomlaan 47MB (NL) | BIM Basis ILS (NL national standard) | 9.9s | 7 pass / 3,623 fail |
| Schependomlaan 47MB | Hand-written "door ≥ 900mm" numeric rule | 5.4s | 92 pass / 113 fail |

Of 113 reported door-width failures, only 12 doors are too narrow; 101 have no width
recorded. Separating those is the product's whole value-add.

## Phase 1 — Reset the repository — **DONE 2026-09-01**

`main` reset to `942b45f`; the nine commits after it discarded. Recovery branch:
`backup/pre-reset-20260901`. Detail in `docs/decisions.md`.

## Phase 2 — The modular monorepo — **DONE 2026-09-02**

The plan at this point called for the thinnest possible Django app: one screen, synchronous,
no tenancy, no queue, no separate frontend. That was reversed deliberately — see
*"A base built to be continued, not a prototype to be thrown away"* in `docs/decisions.md`.
What exists now:

```
packages/engine/     cadgpt_engine — deterministic checking. No framework, no network.
services/api/        Django + DRF + Celery. Six apps, layered by import contract.
services/web/        React + Vite + TanStack Query. TypeScript, RTL-native.
deploy/              Dockerfiles and the compose stack.
```

**Verified running 2026-09-02**, on the container stack, not in a test harness:

```
POST /api/v1/auth/register/          201, account created
POST /api/v1/auth/login/             200, access token in body, refresh in an httpOnly cookie
POST /api/v1/tenants/                201, tenant + owner membership in one transaction
POST /api/v1/media/       (IDS)      201, sha256 recorded, stored under the tenant's prefix
POST /api/v1/rule-sets/              201, IDS parsed: title "Accessible door width", 1 spec
POST /api/v1/media/       (IFC)      201
POST /api/v1/reviews/                201
POST /api/v1/reviews/{id}/check/     202 accepted, run pending
   -> Celery worker, separate container, 0.511s
GET  /api/v1/reviews/{id}/runs/{id}/ 200, status succeeded, outcome FAIL
                                     1 PASS / 1 FAIL / 1 INDETERMINATE
```

The three doors came back as three different answers: one compliant, one measured at 800mm
against a 900mm requirement (`ATTRIBUTE_VALUE_MISMATCH`, FAIL), and one with no width
recorded at all (`ATTRIBUTE_EMPTY`, INDETERMINATE). That distinction, surviving the whole
stack from upload to JSON response, is the thing being built.

Three defects were found by running it that the test suite had not caught, each now covered
by a test: tenant resolution ran as middleware and could never see a JWT-authenticated user;
JWT lifetimes were configured as integers and failed on the first real sign-in; the report
named the storage key instead of the file the architect uploaded.

## Phase 3 — What the first real user needs — **NEXT**

Driven by use, not anticipation. In rough order of what a design office hits first:

- **Report presentation.** Findings grouped by severity, filtered by status, with the
  coverage statement above the findings rather than below them (`prd.md` 5.7). The current
  report view is honest but flat.
- **The web overlay.** A findings list is a document an architect skims; errors drawn on the
  model they just finished is something they act on. ThatOpen Engine or xeokit, both open
  source, both already load BCF viewpoints (`prd.md` 5.8).
- **BCF and PDF export**, through `ifctester`'s own reporters, with a fixture test of our own
  over the BCF output — that reporter has had open defects.
- **Large-model behaviour.** 47MB completes in ten seconds; the failure modes at 500MB are
  unmeasured. Upload directly to object storage rather than through the API process.
- **Invitations and roles in the UI.** The API has membership and roles; the frontend does
  not surface them yet.

## Phase 4 — Toward the PRD

The engine is the oracle everything else in `prd.md` depends on. The next structural pieces,
each of which the current architecture was shaped to receive:

- **The derivation layer** (`prd.md` 5.4) — ifcpatch recipes producing observations, so
  geometric rules become IDS bounds checks. It enters as a package beside the engine and is
  called before `run_check`.
- **Rule packs** (`prd.md` 5.5) — a pack is many IDS files plus clause records, not the
  single file `RuleSet` holds today. `RuleSet` was shaped to grow into it.
- **The coverage manifest** (`prd.md` 5.7) — which clauses were evaluated and which were not.
  It is the reporting half of the same three-valued discipline the engine already applies.
- **Findings as rows**, when dispositions arrive and findings need identity across runs.
  Until then the report is one JSON document, which is what it is used as.

---

## Deliberately not built yet

PostgreSQL row-level security, WebSocket progress, S3 multipart upload authorization, a
transactional outbox, per-tenant rate limits, an admin UI, the agent layer, the connector.
Each is a real concern; none is on the path to the first user. They return when there is
something to protect or someone asking.
