# DEC-0003 — Python 3.12+, managed by uv

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** everything

## Problem
Language and dependency management, for a system whose entire inherited foundation is fixed.

## Constraints
- `prd.md` §6's inventory is Python: `ifcopenshell`, `ifcpatch`, `ifctester`, `ifc5d`,
  `topologicpy`, `ifcclash`, Shapely, GeoPandas, `sectionproperties`, OpenSeesPy.
- I3 forbids reimplementing any of it, so there is no path to another language that does not
  begin by violating an invariant.
- I1 must be enforceable by **dependency isolation** (DEC-0004), so the package manager must
  make disjoint dependency sets across distributions cheap and verifiable.
- Types at every boundary (`CLAUDE.md` §6) — 3.12's typing surface is what `mypy --strict`
  needs to be worth running.

## Options
1. Python 3.12 + uv.
2. Python 3.12 + Poetry — mature, slower resolution, and multi-distribution dependency
   isolation is more awkward to express and verify.
3. A second language for the API layer, with Python behind it — two runtimes, two toolchains,
   two test stories, and a serialization boundary in the middle of the domain, for no gain.

## Decision
Python 3.12+, `uv`, one lockfile, dependency groups per distribution.

## Expected result
`uv sync --group engine` produces an environment in which importing any inference SDK raises
`ImportError`. That is harness gate 4, and it is the proof of I1.

## Reopens if
The connector needs a native component in the host's own runtime — .NET for Revit, for
instance. That is a connector-only decision and does not touch the server.

## Consequences accepted
Python's runtime performance on geometry work. Mitigated by the fact that the heavy paths are
C++ underneath (Open CASCADE, CGAL) and by caching quantities on `(element, convention, model
hash)` if takeoff cost becomes real — never by dropping the convention (`prd.md` §12).
