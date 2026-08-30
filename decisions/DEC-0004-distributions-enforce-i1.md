# DEC-0004 — One repository, several distributions with disjoint dependency sets

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `pyproject.toml`, `src/`, CI

## Problem
I1 says the language model never evaluates a rule. `prd.md` §3 requires it to be a
machine-checked import contract. A lint rule is the obvious implementation, and it is
defeatable by `importlib`, a plugin entry point, or a raw HTTP call to an inference endpoint —
each of which a well-meaning agent under schedule pressure could write without malice.

## Constraints
- I1 must be a **fact**, not a policy. `prd.md` §3: a checker that is deterministic ninety-five
  percent of the time gives no guarantee at all, because the user cannot tell which five
  percent they are looking at.
- The enforcement must be showable to a customer or a regulator.
- The codification service genuinely needs an inference client (`prd.md` §8), so the boundary
  is real and cannot be "no model anywhere".
- The custom surface is small; heavy repository machinery is not affordable and not warranted.

## Options
1. **One distribution, lint-only enforcement.** Simple. Defeatable by three separate mechanisms.
2. **Separate repositories per context.** Undefeatable, and it fragments a codebase whose total
   custom surface is a few thousand lines. Cross-repo change becomes a multi-PR ritual.
3. **One repository, several distributions with disjoint dependency groups**, plus lint.

## Decision
Option 3. `cadgpt-engine` declares no inference SDK and no HTTP client. CI builds an engine-only
environment and asserts that importing one raises `ImportError`.

`codification` may depend on `engine`. `engine` may never depend on `codification` or
`assistance` — and the edge from codification to the engine is a committed file, never a call.

## Expected result
In the engine environment, an inference call is not merely forbidden — it is unresolvable,
regardless of how it is spelled. Gate 3 catches what someone wrote; gate 4 catches what they
could write.

## Reopens if
Never for the engine. The set of distributions grows as contexts appear; the engine's empty
inference set does not change.

## Consequences accepted
Multi-distribution packaging is more setup than a single package, and a shared utility used by
both engine and codification must live in `engine` or be duplicated. Accepted: that pressure
points the right way — toward the engine owning its own vocabulary.
