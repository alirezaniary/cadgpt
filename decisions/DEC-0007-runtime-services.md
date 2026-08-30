# DEC-0007 — FastAPI, Celery + Redis, S3-compatible storage, Docker Compose

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `src/api`, deployment

## Problem
The runtime surface: how a check is requested, how minutes of CPU-bound geometry work are
executed, where model files sit, and what dev and prod run on.

## Constraints
- All product logic runs on the server (`prd.md` §5.1). In the connector phases the client is
  an executor and a renderer with no logic in it.
- A check run is minutes of geometry work — it cannot be a request-response.
- On-prem, inside a customer's own network, is a target deployment, not a variant.
- Typed boundaries (`CLAUDE.md` §6).
- Model files are large and may not leave the customer's network.

## Options
1. FastAPI + Celery/Redis + S3-compatible storage, Docker Compose in dev and the same images
   on-prem.
2. A managed queue and managed object storage. Simpler to operate, and unavailable in the
   deployment that matters.
3. Synchronous checking with a long timeout. Fails on the first real model.

## Decision
Option 1. FastAPI with Pydantic v2 for the surface; Celery with Redis for runs; S3-compatible
object storage, MinIO on-prem. Docker Compose for development, the same images on-prem.

`src/api` holds **no domain logic**. A rule evaluated inside a route handler is unreachable
from a test and unrunnable from the CLI, which breaks `docs/process/definition-of-done.md`
condition 2 — the real path must be executable without an HTTP server.

## Expected result
Every capability is runnable from a CLI over a real model without the API running. The API is a
thin typed surface over the same functions.

## Reopens if
Celery proves heavier than the job count warrants. A single-node queue would be the fallback,
and the domain code would not change, because it does not know about the queue.

## Consequences accepted
Redis as an operational dependency on-prem. Justified by needing retries and observability on
long geometry runs; a queue-less design would reinvent both.
