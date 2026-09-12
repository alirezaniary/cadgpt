# T-0043 — The seeder must survive a race, and speak the application's error language

**Phase:** 3 — What the first real user needs   **Status:** done
**Touches invariants:** none directly. **Not reviewer-gated unless it grows.**

## Why

Found by the T-0030 review, which distinguished what was proven from what was assumed.
Idempotence across a **sequential** re-run is proven — verified twice, by the builder and again
by the coordinator: `0 created, 3 skipped`, row count unchanged. Idempotence across a **race** is
not, and the mechanism cannot provide it.

`services/api/cadgpt/apps/rulepack/services.py:112-137` does
`RulePack.objects.matching(...).first()` and then `create_rule_pack`. Neither is inside
`transaction.atomic()` and neither read takes a lock, so two concurrent
`manage.py seed_rule_packs` — two API replicas running it from an entrypoint, or a per-container
deploy hook — can both pass the pre-check. `full_clean`'s own `validate_unique` is a second
unlocked read that can also pass. Only the database constraint `unique_rule_pack_identity` stops
the duplicate, and it surfaces as an **unhandled `IntegrityError` traceback out of a management
command**, not a graceful "skipped".

Worse, `FileField.pre_save` writes the bytes to storage **before** the INSERT, so the losing
process leaves an orphan file under `rule-packs/<jurisdiction>/` that nothing will ever collect.

**And the manager speaks the wrong error language.**
`repositories/custom_managers.py:105` lets `full_clean` raise Django's
`django.core.exceptions.ValidationError`, which `RulePackService.seed` does not translate —
unlike `services.py:44-48`, where `InvalidIdsError` *is* translated into the application's own
`cadgpt.apps.base.exceptions.ValidationError`. The blast radius today is a traceback instead of a
clean `CommandError`, because the only caller is a management command. The moment anything
HTTP-facing calls `seed`, a blank citation becomes a 500 instead of a 400.

## Scope

- `services/api/cadgpt/apps/rulepack/services.py` — wrap the check-and-create in
  `transaction.atomic()` and catch `IntegrityError`, then re-fetch and report the pack as
  skipped. **`RuleSetService.create` at `services.py:63-66` already uses this pattern** — follow
  it rather than inventing a second idiom.
- Ensure the losing branch does not leave an orphaned file, or collect it if it does.
- `repositories/custom_managers.py` — translate Django's `ValidationError` into the
  application's, the way the rule-set path already does.
- `services/api/cadgpt/apps/rulepack/tests/test_rule_pack_service.py` — it has **no** test for a
  blank or whitespace-only `source_citation`. Add one; the behaviour is correct today and
  untested, which is how correct behaviour stops being correct.
- `services/api/cadgpt/tests/test_tenant_isolation.py` —
  `test_the_rule_pack_catalogue_is_the_same_for_every_tenant` asserts the pack is *in* both
  responses rather than that the two result sets are **equal**. Nothing can differ today, so this
  is not a hole, but set equality would catch a future filter that varied the catalogue by tenant
  and costs nothing.

**Does not change:** the identity key, the skip-rather-than-overwrite behaviour (that is correct
and deliberate — see T-0044), or the model.

## How to prove it ran

The race is the point, so prove it rather than reasoning about it: two concurrent seeds against
the same empty catalogue, both completing without a traceback, one row created. If genuine
concurrency is impractical, drive the collision deterministically — force the pre-check to pass
and let the constraint fire — and say which you did.

`make verify` with the new tests named, and a mutation proof: remove the `IntegrityError`
handling and show the test failing with the real traceback.

## Evidence

**Changes made:**
- `services/api/cadgpt/apps/rulepack/services.py` — `RulePackService.seed`'s
  check-and-create is now wrapped in `transaction.atomic()` and the surrounding
  `except IntegrityError` re-fetches via `RulePack.objects.matching(...).first()` and
  reports the pack the winner created as skipped (`created=False`), the same
  try/`transaction.atomic()`/except idiom `RuleSetService.create` already uses.
- `services/api/cadgpt/apps/rulepack/repositories/custom_managers.py` —
  `RulePackManager.create_rule_pack` now: (1) catches `django.core.exceptions.
  ValidationError` from `full_clean()` and re-raises `cadgpt.apps.base.exceptions.
  ValidationError` (mirrors `AccountService.register`'s translation), and (2) catches
  `IntegrityError` from `save()` and calls `rule_pack.source_file.delete(save=False)`
  before re-raising, so the losing side of a race does not leave an orphan file under
  `rule-packs/<jurisdiction>/` — `FileField.pre_save` already wrote those bytes to
  storage before the INSERT that just failed.
- `services/api/cadgpt/apps/rulepack/tests/test_rule_pack_service.py` — added
  `test_a_blank_or_whitespace_only_citation_is_refused` (parametrized `""` and `"   "`)
  and `test_a_race_that_passes_every_unlocked_read_still_creates_only_one_row`.
- `services/api/cadgpt/tests/test_tenant_isolation.py` —
  `test_the_rule_pack_catalogue_is_the_same_for_every_tenant` now asserts the two
  tenants' result sets are equal, not merely that each contains the pack.
- Not touched, per scope: the identity key, the skip-rather-than-overwrite behaviour,
  the model.

**`make verify`:** passes in full (this environment lacks a system `gettext`/`msgfmt`
package and no sudo; a previous session's extracted copy at
`/tmp/claude-1000/.../scratchpad/gettext-local/usr/bin/msgfmt` was put on `PATH`/
`LD_LIBRARY_PATH` to satisfy `compile-messages`, which `make test` depends on — nothing
in the repository changed for this). Full run:
```
uv run ruff check .                    -> All checks passed!
uv run ruff format --check .           -> 191 files already formatted
uv run mypy packages/engine/src services/api/cadgpt   -> Success: no issues found in 173 source files
uv run lint-imports --no-cache         -> Contracts: 5 kept, 0 broken.
uv run pytest                          -> 296 passed, 34 warnings in 4.52s
cd services/web && pnpm run verify     -> lint (2 pre-existing warnings, 0 errors),
                                           typecheck, build, build-workbench,
                                           test-unit (2 passed), test-storybook (35 passed)
                                           all green
```

**Real path — genuine concurrency, not deterministic-only** (the task allows either;
this used real concurrency against the actual stack `make up` runs, on top of the
deterministic in-suite test below): the running dev stack's Postgres
(`localhost:5433`, the same database `cadgpt-api-1`/`cadgpt-worker-1` use) already held
all 10 manifest packs from an earlier `seed_rule_packs` run. The `("sample", "", "0.1",
"Accessible door width")` row was deleted to reopen that one identity's race window,
then two real OS processes were launched at the same time, each running the actual
`RulePackService().seed(...)` (the same call `manage.py seed_rule_packs` makes) against
that real database, from the local checkout carrying this fix. A 2-second sleep was
injected into `RulePackQuerySet.matching` from the *driver script only* (not shipped
code) to widen the race window past sub-millisecond luck — two genuinely separate
processes and DB connections still do the racing and the actual commit/rollback.

Command (`/tmp/race_seed.py`, driver only, not part of the fix):
```
uv run --project /home/alireza/Projects/cadgpt python /tmp/race_seed.py A > /tmp/race_a.log 2>&1 &
uv run --project /home/alireza/Projects/cadgpt python /tmp/race_seed.py B > /tmp/race_b.log 2>&1 &
wait
```
Output, both processes, no traceback in either:
```
=== A ===
... event=rule_pack_seed_lost_race ... rule_pack_id=f7c72450-27b0-4a15-b31c-5bc63e4aac2b ...
A: created=False uuid=f7c72450-27b0-4a15-b31c-5bc63e4aac2b
=== B ===
... event=rule_pack_seeded ... rule_pack_id=f7c72450-27b0-4a15-b31c-5bc63e4aac2b ...
B: created=True uuid=f7c72450-27b0-4a15-b31c-5bc63e4aac2b
```
Verified after: exactly one row for that identity in Postgres (`uuid=f7c72450-...`) and
exactly one file under `services/api/mediafiles/rule-packs/sample/` — the loser's write
did not survive as an orphan. Catalogue count is back to 10 (the deleted row was
recreated by the race itself).

**Real path — deterministic, in the automated suite** (per "How to prove it ran": drive
the collision deterministically since sqlite `:memory:` cannot host two real
connections against one schema): `test_a_race_that_passes_every_unlocked_read_still_
creates_only_one_row` forces the second `seed()` call's identity pre-check
(`RulePackQuerySet.matching`) and `full_clean`'s constraint check
(`RulePack.validate_constraints`) to both miss, exactly as a real race's second
transaction would, leaving only `unique_rule_pack_identity` itself to stop the
duplicate:
```
uv run pytest services/api/cadgpt/apps/rulepack/tests/test_rule_pack_service.py services/api/cadgpt/tests/test_tenant_isolation.py -q
-> 17 passed
```

**Mutation proof:** the `except IntegrityError` block in `RulePackService.seed` was
removed and the race test re-run:
```
django.db.utils.IntegrityError: UNIQUE constraint failed: rulepack_rulepack.jurisdiction, rulepack_rulepack.region, rulepack_rulepack.version, rulepack_rulepack.name
services/api/cadgpt/apps/rulepack/services.py:131: in seed
    rule_pack = RulePack.objects.create_rule_pack(
services/api/cadgpt/apps/rulepack/repositories/custom_managers.py:118: in create_rule_pack
    rule_pack.save(using=self._db)
FAILED services/api/cadgpt/apps/rulepack/tests/test_rule_pack_service.py::test_a_race_that_passes_every_unlocked_read_still_creates_only_one_row
```
The fix was then restored (`diff` against the pre-mutation copy showed the file
identical afterwards) and the full suite re-verified green.

**Wiring:** the fixed `seed()` is the same method the real entry point already calls,
unchanged by this task —
`services/api/cadgpt/apps/rulepack/management/commands/seed_rule_packs.py:111-117`:
```python
pack, was_created = service.seed(
    ids_path=ids_path,
    jurisdiction=entry.jurisdiction,
    region=entry.region,
    version=entry.version,
    source_citation=entry.source_citation,
)
```
And the two try/except additions that are the substance of this task —
`services/api/cadgpt/apps/rulepack/services.py:131-145`:
```python
        try:
            with transaction.atomic():
                rule_pack = RulePack.objects.create_rule_pack(
                    ...
                )
        except IntegrityError:
            ...
            existing = RulePack.objects.matching(
                jurisdiction=jurisdiction, region=region, version=version, name=name
            ).first()
```
`services/api/cadgpt/apps/rulepack/repositories/custom_managers.py:109-127`:
```python
        try:
            rule_pack.full_clean(exclude=["source_file"])
        except DjangoValidationError as exc:
            raise ValidationError(...) from exc

        try:
            rule_pack.save(using=self._db)
        except IntegrityError:
            rule_pack.source_file.delete(save=False)
            raise
```

**NOT DONE:** nothing. All scope items landed: atomic wrap + `IntegrityError` skip
path, orphan-file cleanup, `ValidationError` translation in the manager, the blank/
whitespace-citation test, and the tenant-isolation set-equality assertion.

## Review
