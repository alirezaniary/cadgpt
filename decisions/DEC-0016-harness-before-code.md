# DEC-0016 — The harness is built before the code it guards, and every guard ships with a proof it fails

**Status:** DECIDED
**Date:** 2026-08-30
**Decided by:** Lead
**Affects:** `Makefile`, `tools/`, P0

## Problem
Sixteen mechanical gates are the mechanism that makes generated code trustworthy
(`docs/architecture/harness.md`). Two questions follow: when are they built, and how do we know
a gate is doing anything?

The second is subtler. A guard that has never rejected anything is indistinguishable from a
guard that scans nothing, silently matches nothing, or was misconfigured — and that guard reads
as green forever.

## Constraints
- Guards added after code find violations in modules that already have dependents. Added first,
  they find violations in the diff that creates them.
- DEC-0013: prerequisite order is absolute, and everything under `src/` depends on the guards.
- `prd.md` §2 and this workspace's own history: a suite can pass while the system is broken.
  That applies to the guards themselves.

## Options
1. Guards as needed, alongside the code they check. Each arrives after something it should have
   caught, and there is no moment at which the set is known to be complete.
2. All guards up front, with no proof each works. Green from day one, meaning nothing.
3. All guards up front, **each shipped with a test that proves it fails on a deliberately bad
   input**.

## Decision
Option 3. P0 is the first task after this framework: `make verify` runs all sixteen gates over
an empty repository and passes, and each gate has a companion test feeding it a violation and
asserting a non-zero exit.

The jurisdiction guard gets a file with a code reference in an identifier. The quote linter gets
a record whose bound disagrees with its quote. The placeholder scan gets a `TODO`. The
isolation probe gets an environment with an inference SDK installed. Each must fail.

## Expected result
On the day the first module is written, every constraint in `CLAUDE.md` §3 is already enforced,
and every gate has demonstrated that it can reject. A green `make verify` means the gates ran
and found nothing — not that they found nothing to look at.

## Reopens if
Never. New guards are added under the same rule: a guard without a proof it fails is not merged.

## Consequences accepted
P0 is a real piece of work producing no product functionality, and it sits on the critical path
before anything visible. Accepted: it is the cheapest point at which this cost can ever be paid.
