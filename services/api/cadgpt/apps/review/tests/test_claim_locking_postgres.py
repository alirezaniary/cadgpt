"""T-0050: `_claim`'s row lock across a nullable `review__rule_set` join, proven against
real Postgres, not merely described.

Only Postgres enforces the restriction this test guards -- sqlite (`make verify`'s
backend, `cadgpt.config.settings.test`) accepts `SELECT ... FOR UPDATE` across any join,
nullable side or not, so this regression cannot live in the hermetic suite at all: it
would pass unconditionally there and prove nothing about the defect it exists to catch.
It is marked `postgres` and runs under `make test-postgres`
(`cadgpt.config.settings.test_postgres`), against the real Postgres `make up` already
starts. See `docs/decisions.md`, "Postgres-only regressions get a marked suite, not a
slower `make verify`".

T-0031's real defect, reproduced here rather than narrated: making `Review.rule_set`
nullable turned `review__rule_set` into a LEFT OUTER JOIN for any review with no uploaded
rule set. `CheckRunExecutor._claim`'s `select_for_update()` locked across that join until
it was narrowed to `of=("self",)`. Postgres refuses to lock the nullable side of an outer
join -- `django.db.NotSupportedError: FOR UPDATE cannot be applied to the nullable side
of an outer join` -- and sqlite never raises it, which is exactly how the original defect
shipped past a green `make verify` and was only caught by running the real stack.
"""

from __future__ import annotations

import pytest

from cadgpt.apps.review.models import Review
from cadgpt.apps.review.services import ReviewService
from cadgpt.apps.review.services.execution import CheckRunExecutor
from cadgpt.apps.rulepack.models import RulePack
from cadgpt.apps.tenancy.models import Tenant

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


def test_claim_locks_a_run_whose_review_has_no_rule_set(
    tenant: Tenant, catalogue_review: Review, rule_pack: RulePack
) -> None:
    """`_claim` must succeed for a run whose review's `rule_set` is null.

    `catalogue_review` (conftest.py) is exactly T-0031's shape: no uploaded `RuleSet`, so
    `review.rule_set_id` is `None` and `select_related("review__rule_set")` compiles to a
    LEFT OUTER JOIN. The run is created through `ReviewService.request_check` -- the real
    path a tenant's request takes, not a bare `CheckRun.objects.create` -- because that is
    what puts a genuine `NULL` on the join's far side rather than fabricating the shape of
    the defect by hand.

    With `select_for_update(of=("self",))` in place, this passes. Reverting that one
    argument in `CheckRunExecutor._claim` (`execution.py`) reproduces T-0031's exact
    failure against this same test: Postgres raises `NotSupportedError` before any claim
    logic runs at all, and the assertions below are never reached. Both runs are pasted in
    the task file's Evidence.
    """
    run = ReviewService(tenant=tenant).request_check(
        review=catalogue_review, rule_pack_uuids=[str(rule_pack.uuid)]
    )
    assert run.review.rule_set_id is None  # the nullable side the outer join is over

    claimed = CheckRunExecutor()._claim(run.uuid)

    assert claimed.uuid == run.uuid
    assert claimed.claim_count == 1
