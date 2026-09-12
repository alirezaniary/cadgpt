"""Tests marked `postgres`: database behaviour Postgres enforces and sqlite does not.

`cadgpt.config.settings.test` runs the whole suite against sqlite in memory, which is
what keeps `make verify` fast and hermetic -- and which is exactly why T-0031's defect
(`select_for_update()` locking across `review__rule_set`, nullable and therefore a LEFT
OUTER JOIN once T-0031 landed) was invisible there: sqlite does not enforce "FOR UPDATE
cannot be applied to the nullable side of an outer join", Postgres does, and only running
against a real Postgres surfaces it. See `docs/decisions.md`, "Postgres-only regressions
get a marked suite, not a slower `make verify`" (T-0050).

Everything else about the test environment is unchanged -- eager Celery, in-memory
storage, MD5 password hashing -- only `DATABASES` moves from sqlite to a real Postgres.
The target is the same server `make up` already starts: `TEST_POSTGRES_DATABASE_URL`
defaults to the same `DATABASE_URL` a developer's `.env` already points at the compose
stack's Postgres (`deploy/compose.yaml`'s host-exposed `${POSTGRES_HOST_PORT:-5433}`), so
running `make test-postgres` after `make up` needs no extra configuration. Django's test
runner creates and destroys its own `test_<NAME>` database against that connection; it
never touches the development database these credentials also open.
"""

from __future__ import annotations

from cadgpt.config.settings.base import env
from cadgpt.config.settings.test import *

DATABASES = {
    "default": env.db(
        "TEST_POSTGRES_DATABASE_URL",
        default="postgres://cadgpt:cadgpt@localhost:5433/cadgpt",
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
