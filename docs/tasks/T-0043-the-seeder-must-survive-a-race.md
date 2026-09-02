# T-0043 — The seeder must survive a race, and speak the application's error language

**Phase:** 3 — What the first real user needs   **Status:** open
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

<!-- the builder writes this -->

## Review
