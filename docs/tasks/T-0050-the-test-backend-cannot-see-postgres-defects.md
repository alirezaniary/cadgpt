# T-0050 — The suite cannot catch the class of defect that only Postgres enforces

**Phase:** 3   **Status:** done
**Touches invariants:** none, but this is about the evidence standard itself.

## Why

Found by the T-0031 review, and demonstrated by T-0031 itself. When `Review.rule_set` became
nullable, `CheckRunExecutor._claim`'s `select_for_update()` over `select_related("review__rule_set")`
became a lock across a LEFT OUTER JOIN. `make verify` was green throughout — sqlite does not
enforce the restriction — and the first real check against the compose stack's Postgres failed
with `NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join`.

It was found by running the stack, which is the fifth defect in this repository found that way
rather than by its suite. The fix (`select_for_update(of=("self",))`) is correct and is one line;
what is unguarded is the **class**. Nothing in the suite would catch its reintroduction, and the
only proof it works is a manual compose run pasted into a task file. The next nullable relation
added to a locked queryset reproduces it exactly, and reproduces it in production.

This is the repository's documented failure mode stated precisely: a green suite over a system
that does not work, because the test backend is not the production backend.

## Scope

**Changes**

- The tests that exercise database behaviour Postgres enforces and sqlite does not run against
  **Postgres**. The compose stack already has one; the decision is whether that is a separate
  marked suite, a CI-only backend switch, or `make verify` moving to Postgres wholesale.
  `make verify` is required to stay fast and hermetic, which argues against the last — but say
  which was chosen and why, because this decision outlives the task.
- A regression test that fails on the T-0031 defect specifically: `_claim` locking across a
  nullable outer join.
- The choice recorded in `docs/decisions.md`.

**What explicitly does not change**

- `make verify`'s speed and hermeticity, unless the evidence argues the trade is worth it.
- The `select_for_update(of=("self",))` fix, which is already correct.

## How to prove it ran

Revert the `of=("self",)` fix and show the new test **failing** — against Postgres — then restore
it and show it passing. That mutation is the whole task: a guard that does not fail on the
original defect is not a guard. Paste both runs, and state the wall-clock cost added to whichever
gate now runs against Postgres.

## Evidence

### Decision taken

A separate marked suite and `make test-postgres` target, not a CI-only backend switch and
not moving `make verify` to Postgres wholesale. `make verify` stays on sqlite and stays fast;
Postgres-only regressions are marked `pytest.mark.postgres`, excluded from `make verify` by
`-m "not postgres"`, and run explicitly against the compose stack's real Postgres by
`make test-postgres`. This is the same shape as `make e2e`: a real-infrastructure gate kept
separate from the hermetic one, not merged into it. Recorded in `docs/decisions.md`.

### Wiring

`Makefile`:

```
test: compile-messages  ## The whole suite, engine and service (sqlite; `postgres`-marked tests excluded, see test-postgres)
	$(UV) pytest -m "not postgres"

test-postgres: compile-messages  ## Database behaviour sqlite does not enforce -- needs `make up`'s real Postgres
	$(UV) pytest -m postgres --ds=cadgpt.config.settings.test_postgres
```

`pyproject.toml` (`[tool.pytest.ini_options]`), `--strict-markers` is set, so an unregistered
marker is a collection error, not a silent no-op:

```
markers = [
    "integration: enters at a real entry point over real files and exits at a real output",
    """postgres: exercises database behaviour Postgres enforces and sqlite does not; run \
with `make test-postgres` (--ds=cadgpt.config.settings.test_postgres) against the compose \
stack's real Postgres, never collected by the hermetic `make verify`""",
]
```

`services/api/cadgpt/apps/review/tests/test_claim_locking_postgres.py` carries
`pytestmark = [pytest.mark.django_db, pytest.mark.postgres]`, so it is collected by
`test-postgres` and excluded by `test`'s `-m "not postgres"`.

### 1. `make verify` — still green, still fast

Full run, real exit code captured directly (not through a pipe to `tail`, which had
previously masked a `web-verify` failure as exit 0):

```
$ { time make verify > /tmp/verify_full.log 2>&1; echo "MAKE_VERIFY_EXIT=$?" >> /tmp/verify_full.log; }
...
uv run pytest -m "not postgres"
...
306 passed, 1 deselected, 35 warnings in 6.43s
cd services/web && pnpm install --frozen-lockfile && pnpm run verify
...
 Test Files  1 passed (1)
      Tests  2 passed (2)
...
 Test Files  9 passed (9)
      Tests  36 passed (36)
MAKE_VERIFY_EXIT=0

real	1m18.204s
user	1m50.483s
sys	0m14.838s
```

`306 passed, 1 deselected` -- the deselected test is the one new `postgres`-marked test,
confirmed excluded from the hermetic run. `lint`, `types` (`mypy --strict`, "Success: no
issues found in 176 source files"), and `contracts` ("Contracts: 5 kept, 0 broken.") all
passed earlier in the same run (see full log; trimmed here for length). Wall clock: 1m18s,
same order of magnitude as before this task -- the new Postgres suite adds nothing to this
gate's cost because it never runs here.

An earlier attempt at this same run (`time make verify 2>&1 | tail -150`) reported exit 0
while `web-verify`'s Storybook interaction suite had actually failed with three browser
timeouts (`make: *** [Makefile:45: web-verify] Error 1`) -- caused by the pipe to `tail`
returning `tail`'s exit code, not `make`'s, plus real resource contention from other
concurrent work in this session. Confirmed as environmental, not a regression from this
task's changes: with this task's changes stashed (`git stash`), a plain `make web-verify` on
that clean tree passed cleanly in 1m11s (`Test Files 9 passed (9)`, `Tests 36 passed (36)`).
This task touches no frontend file.

### 2. `make test-postgres` against the real Postgres — passes

`make up`'s Postgres was already running (`docker compose -f deploy/compose.yaml ps`:
`cadgpt-postgres-1 ... Up 36 hours (healthy) ... 0.0.0.0:5433->5432/tcp`):

```
$ make test-postgres
cd services/api && uv run --project .. python manage.py compilemessages
File "…/cadgpt/locale/fa/LC_MESSAGES/django.po" is already compiled and up to date.
uv run pytest -m postgres --ds=cadgpt.config.settings.test_postgres
.                                                                        [100%]
1 passed, 306 deselected in 8.478s
```

`1 passed, 306 deselected` -- the one `postgres`-marked test runs, and the whole hermetic
suite is correctly deselected under this backend.

### 3. Mutation proof — the guard actually catches the defect

`_claim` reverted from `select_for_update(of=("self",))` to bare `select_for_update()` in
`services/api/cadgpt/apps/review/services/execution.py`, then `make test-postgres` re-run
against the same real Postgres:

```
$ make test-postgres
...
uv run pytest -m postgres --ds=cadgpt.config.settings.test_postgres
F                                                                        [100%]
=================================== FAILURES ===================================
_____________ test_claim_locks_a_run_whose_review_has_no_rule_set ______________
...
E           django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
...
services/api/cadgpt/apps/review/services/execution.py:290: in _claim
    .first()
...
FAILED services/api/cadgpt/apps/review/tests/test_claim_locking_postgres.py::test_claim_locks_a_run_whose_review_has_no_rule_set - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the null...
1 failed, 306 deselected in 4.15s
make: *** [Makefile:42: test-postgres] Error 1
EXIT=2
```

This is T-0031's exact defect, reproduced against the real database rather than narrated:
the assertions in the test body are never reached (the traceback stops inside `_claim`
itself, at the `.first()` call), and the raised exception is the literal
`django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an
outer join` -- proving sqlite's silence was masking a real Postgres restriction, and proving
this guard fails on the original defect rather than passing unconditionally.

`select_for_update(of=("self",))` restored (`git diff services/api/cadgpt/apps/review/services/execution.py`
is empty, confirming a clean revert), then re-run:

```
$ make test-postgres
...
uv run pytest -m postgres --ds=cadgpt.config.settings.test_postgres
.                                                                        [100%]
1 passed, 306 deselected in 6.21s
EXIT=0
```

Passes again.

### 4. Wall-clock cost of `make test-postgres`

8.5s, 8.7s and 14.1s wall clock across the three runs above (`time` around each `make
test-postgres` invocation) -- effectively the interpreter/Django-startup floor plus one test
against an already-running Postgres, no container start included since `make up` was already
up. This is informational, not a regression: `test-postgres` is a separate gate from `make
verify` by design (see Decision above) and is expected to run only when a developer or CI
job explicitly opts into exercising Postgres-specific behaviour, the same way `make e2e` is
a separate, opt-in real-browser gate already.

## Review
