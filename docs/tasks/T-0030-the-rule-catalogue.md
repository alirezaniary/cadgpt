# T-0030 — The rule catalogue: rules we ship, belonging to no tenant

**Phase:** 3 — What the first real user needs   **Status:** open
**Touches invariants:** **tenancy**, and the import contracts. **Reviewer-gated**, without
exception — this is the one invariant this repository enforces structurally rather than by
memory, and this task is the first thing that does not fit it.

## Why

Scope settled 2026-09-02 (`docs/decisions.md`, `prd.md` §12): **rules are a catalogue we ship,
not a file the architect uploads.** The user selects by jurisdiction, region and version, and
that selection becomes part of the job record. User-uploaded rule sets already work, are not
being removed, and are simply no longer the primary path.

Today the only way rules enter the system is `RuleSet` — a `TenantOwnedModel` holding one
uploaded IDS file. That is the right model for a rule set an office authored. It is the wrong
model for a pack we publish to everyone, and the reason is structural, not stylistic.

## The structural constraint — read this before writing any code

`CLAUDE.md`: *every tenant-owned table carries `tenant`, every read goes through `for_tenant`,
and a structural test fails the build if a viewset escapes the scoped base class. There is no
row-level security behind it.* That test is the whole enforcement mechanism.

A shipped pack belongs to **no tenant**. The tempting move — make `RuleSet.tenant` nullable —
puts a nullable column at the centre of that invariant and turns every `for_tenant` call site
into something a reader has to reason about instead of trust. **It is refused** (`docs/plan.md`,
Phase 3). The catalogue is a **separate model**, so `for_tenant` stays total and there is no
exception to hold in your head.

That decision creates the real problem this task has to solve honestly: **a global catalogue
needs a viewset that is deliberately not tenant-scoped**, and the structural test exists
precisely to fail that. Do not weaken the test, do not add a blanket exemption, and do not
special-case by class name in a way that would also let a genuinely tenant-owned viewset
through. What is needed is an explicit, narrow, *declared* category — a viewset that serves a
model owning no tenant data at all — such that the test still fails for anything holding tenant
rows. **If you cannot do that without weakening the guarantee, stop and say so in the task file
rather than shipping a hole.** That answer is an acceptable outcome of this task; a quiet bypass
is not.

## Scope

**Changes**

- `services/api/cadgpt/apps/rulepack/models.py` — a `RulePack` model beside `RuleSet`. **Not**
  `TenantOwnedModel`. It carries at minimum: a name, the IDS source file, jurisdiction, region,
  version, and a **source citation** — where this pack came from and who published it, because
  `prd.md` §5.7 requires every finding to carry attribution, and a pack we ship is asserting
  something under our name. Reuse `RuleSet`'s existing parsed-at-upload fields
  (`title`, `author`, `version`, `specification_count`) where they mean the same thing rather
  than inventing parallel names.
- A migration.
- Read-only API to list and retrieve packs, filterable by jurisdiction, region and version.
  Every tenant sees the same catalogue; no tenant can write to it.
- **A seeding path** — a management command that loads packs from IDS files on disk and is
  **idempotent**, so re-running it does not duplicate rows and does not silently overwrite a
  pack a run already cites. `CLAUDE.md`: every background task is idempotent; a seeder is held
  to the same standard.
- Tests, including a structural one asserting that no tenant can reach another tenant's data
  through the new surface, and that the catalogue is readable by all.

**What explicitly does not change**

- `RuleSet` — it stays exactly as it is, tenant-owned, and user upload keeps working. This task
  adds a path beside it; it does not migrate, deprecate or touch the existing one.
- **No rule content.** This loop builds the store, the metadata, the selection surface and the
  seeding path. The product owner authors the packs — Iranian building code first, then EU and
  US — in a separate thread. Seed with whatever public IDS is already in the repository's
  fixtures so the path is exercised; **do not author building code**, and do not invent
  jurisdictions, region codes or version strings for packs that do not exist.
- Selection at check time is **T-0031**, not this task. Build the store; do not wire it into
  the run yet.
- No clause records, no YAML compilation, no ratification pipeline — those are Phase 4
  (`prd.md` §5.5).

## How to prove it ran

`make verify` — and the **5 import contracts must still be kept**; a new model reaching across
a layer is exactly what they are there to catch.

Then the real path, against the running stack, not a test client:

```sh
make up
# seed, twice, to prove idempotence
docker compose -f deploy/compose.yaml exec api python manage.py <the seed command>
docker compose -f deploy/compose.yaml exec api python manage.py <the seed command>
```

The evidence must show:

1. Both seed runs' output, and a row count after each proving the second created nothing.
2. A real HTTP request against the running API listing the catalogue, with the response body
   pasted, and the same request filtered by jurisdiction.
3. **Two tenants, one catalogue**: the same request authenticated as two different tenants
   returning the same packs — and a write attempt against the catalogue being refused.
4. **Wiring**: the migration at head (`showmigrations` output), the route registered in the
   router quoted from the file, and the management command discoverable by `manage.py help`.
5. How you satisfied the structural viewset test without weakening it — quote the test and the
   declaration that makes the catalogue viewset legal under it.

## Evidence

<!-- the builder writes this -->

## Review
