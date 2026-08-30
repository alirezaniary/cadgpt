# DEC-0006 — PostgreSQL 16 with PostGIS

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `engine/resolution`, the parcel channel, deployment

## Problem
Where project facts, adoptions, entitlements, departures, runs, findings and dispositions
live — and, decisively, where parcel geometry lives.

## Constraints
- `prd.md` §5.3 makes the parcel a **first-class second input channel**: site coverage, density
  and setback are checked against a cadastral boundary and a zoning envelope, joined to the
  model by georeferencing.
- Those are among the highest-frequency rejection categories in real plan review, so this is
  not a peripheral feature.
- On-premise deployment is a requirement (`prd.md` §5.9, §5.10), so a managed spatial service
  is not available.
- Dispositions must survive re-runs and re-attach by stable finding identity — relational,
  long-lived, queryable state.

## Options
1. PostgreSQL + PostGIS.
2. PostgreSQL, parcel geometry handled in-process with Shapely. Every spatial query loads
   candidate parcels into memory, and the spatial index has to be reimplemented — against I3.
3. A document store. Adoptions, overlays, entitlements and departures form a dependency closure
   resolved by traversal; that is a relational problem wearing a different hat.

## Decision
PostgreSQL 16 + PostGIS, SQLAlchemy 2.0, Alembic. GDAL/OGR, Shapely and GeoPandas handle
ingest and transformation (`prd.md` §6); PostGIS handles storage, indexing and the join.

## Expected result
The parcel join is a spatial query with an index behind it, and adding a jurisdiction's
cadastral adapter touches only the adapter — never the join, never the checks that consume it.

## Reopens if
Gate 4 returns that parcel data is unobtainable in the first market. That does not remove
PostGIS — the schema still models a parcel — but it moves the two dependent checks into the
coverage manifest as a declared out-of-scope entry, which is exactly what the manifest is for.

## Consequences accepted
A spatial extension in the deployment, including on-prem. Standard, packaged, well-understood.
