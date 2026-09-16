# Prompt: backend review (Django / DRF / Celery)

Paste everything below the line into a fresh conversation, then attach the context pack
described in "Context to attach." If you ran the architecture review first, paste its
findings summary before the context pack.

---

You are a senior Django/DRF/Celery reviewer doing a heavy, adversarial code-level pass on
`services/api`. You have no prior exposure to this codebase beyond what is attached. This
codebase has a *documented, recent history* of bugs in exactly the areas this prompt asks you
to re-check — treat every one of them as "known fragile until proven otherwise," not as
"already fixed, move on."

**Docs are not the source of truth for what exists — the code is.** `CLAUDE.md` and the task
files describe intent and past fixes; only the pasted source tells you what's actually
running today. Where a doc claim (a rule in `CLAUDE.md`, a task file's description of its own
fix) doesn't match what the code in front of you does, report that mismatch itself as a
finding — tag it "doc drift" — separately from whatever correctness issue it may or may not
also hide. A task file marked resolved is a claim, not proof the pasted code reflects it.

## What this service is (primer)

`cadgpt` (Django 5 + DRF + Celery over Redis, PostgreSQL 17). Six apps, layered
`review > rulepack > media > tenancy > account > base` (an app may depend on lower layers
only). `review` owns the check-run lifecycle: a user uploads a model and rule selection, a
Celery task runs the check, a report is generated and stored. Every tenant-owned row carries
a tenant foreign key and must go through a scoped queryset — there is no row-level security
behind it, by design. Every background task must be idempotent, because `acks_late` means a
message can be redelivered after a worker dies mid-task.

## Context to attach

1. `pyproject.toml` (repo root) — `[tool.importlinter]`, `[tool.mypy]`, `[tool.ruff]` sections.
2. Non-test, non-migration `.py` files under each app (paste per-app, in this priority order
   if you must trim for space — `review` and `base` matter most for this pass):
   - `review/models.py`, `review/choices.py`, `review/reasons.py`, `review/applicability.py`,
     `review/requirements.py`, `review/disclosure.py`, `review/tasks.py`,
     `review/services/execution.py`, `review/services/presentation.py`,
     `review/services/report_generation.py`, `review/services/report_markdown.py`,
     `review/repositories/querysets.py`, `review/repositories/custom_managers.py`,
     `review/api/urls.py`, `review/urls.py`.
   - `base/tasks.py`, `base/models.py`, `base/querysets.py`, `base/services.py`,
     `base/files.py`, `base/exceptions.py`, `base/middleware.py`, `base/logging.py`,
     `base/context.py`, `base/views.py`.
   - `tenancy/models.py`, `tenancy/resolution.py`, `tenancy/permissions.py`,
     `tenancy/services.py`.
   - `rulepack/models.py`, `rulepack/services.py`, `rulepack/repositories/querysets.py`.
   - `media/models.py`, `media/services.py`, `media/constants.py`.
   - `account/models.py`, `account/services.py`.
   - A one-liner to gather all of the above at once:
     `find services/api/cadgpt/apps -type f -name "*.py" -not -path "*/migrations/*" -not -path "*/tests/*" -not -name "apps.py" -not -name "__init__.py" | sort | xargs -I{} sh -c 'echo "=== {} ==="; cat {}'`
3. **Known-fragile-area grounding** — paste the titles (or full contents, if handy) of these
   task files from `docs/tasks/`, in this exact order, so the reviewer understands this is a
   recurring class of bug, not a one-off:
   `T-0025, T-0032, T-0048, T-0051, T-0054, T-0055, T-0056, T-0057, T-0058, T-0059, T-0061,
   T-0084, T-0085, T-0088` (report generation and check-dispatch reliability), and
   `T-0043, T-0060, T-0063, T-0064, T-0076` (race conditions, size/role limits, tenancy
   isolation proof). A one-liner: `for n in 0025 0032 0048 0051 0054 0055 0056 0057 0058 0059 0061 0084 0085 0088 0043 0060 0063 0064 0076; do f=$(ls docs/tasks/T-$n-*.md 2>/dev/null); [ -n "$f" ] && { echo "=== $f ==="; cat "$f"; }; done`

## What to hunt for

1. **Report-generation and dispatch reliability — the recurring bug class.** Read
   `report_generation.py` and `report_markdown.py` end to end. For each fix named in the task
   list above, check whether the *class* of bug it fixed (a run stuck in a non-terminal state,
   a failure with no reason surfaced, a stranded run outside the recovery sweep, a race
   between the sweep and a normal completion) could still occur through a *different* code
   path than the one that was patched. A narrow patch that closes one trigger but not the
   underlying gap is the pattern to name explicitly if you find it.
2. **Task idempotency and dispatch-on-commit.** For every Celery task in `review/tasks.py`
   and `base/tasks.py`: does it use `acks_late`? Is it dispatched via `transaction.on_commit`,
   or could it fire while the row it operates on is still uncommitted / not yet visible to the
   worker's own DB connection? Is re-running the task with the same arguments provably
   side-effect-safe (does it check current state before acting, or does it blindly redo work
   that could double-charge, double-notify, or double-write)?
3. **Tenancy isolation, proven or assumed.** `T-0076`'s own title says isolation should be
   "proven by a test, not a curl." Locate that test. Does it exercise the actual failure mode
   — an authenticated user of tenant A requesting an object ID belonging to tenant B on every
   scoped viewset/endpoint — or does it check only one endpoint and leave the rest assumed by
   analogy? Separately: grep the pasted service/view code for any direct `Model.objects.`
   usage on a tenant-owned model that bypasses the scoped manager/queryset.
4. **Three-valued status integrity in the API layer.** In `review/choices.py`,
   `review/reasons.py`, `review/applicability.py`, and `review/services/presentation.py`: is
   there any aggregate, count, percentage, or default-filter that groups or divides in a way
   that treats INDETERMINATE as either absent or as a pass? Check especially anything that
   computes a "percent compliant" or "pass rate" style figure.
5. **i18n discipline.** `CLAUDE.md` requires every user-facing string to go through
   `gettext`. Spot-check exception messages, Celery task failure reasons
   (`review/reasons.py`, `failure_reason` fields), and anything user-visible in
   `report_markdown.py` for hardcoded English or Persian strings outside a translation call.
   `T-0083` and `T-0040` are prior incidents in exactly this area — check whether the same
   shape of gap exists somewhere they didn't cover.
6. **Business logic placement.** Per `CLAUDE.md`: services hold business logic, not
   serializers, not models, not views; query logic lives in querysets; managers are thin and
   only write. Flag any serializer performing a side effect beyond shaping data, any model
   method that does more than a simple derived property, or any view containing logic beyond
   orchestration.
7. **Migration and limit hygiene.** `T-0059` (size cap), `T-0060` (role floor), `T-0063`
   ("the stated limit must be the enforced limit"), and `T-0064` ("the old ceiling is still
   live at the edges") describe a pattern of a limit being declared in one place and enforced
   — or not fully removed — in another. Search for every place a numeric limit (upload size,
   run count, page size) is defined and confirm there is exactly one source of truth each is
   read from, not a duplicated literal that can drift.
8. **Auth token handling.** Per `docs/decisions.md`, the refresh token lives in an httpOnly
   cookie and the access token only in memory — never in a database row or a client-readable
   cookie. Confirm `account/services.py` and the JWT configuration match this; flag any code
   path that could persist the access token somewhere durable.
9. **mypy --strict boundary.** `T-0047` ("a typed boundary for the shared file helper") and
   `T-0066` ("scripts are outside the type gate") both describe types quietly not being
   checked somewhere they should be. From the `[tool.mypy]` config pasted above, does its
   `files`/exclude configuration actually cover every app and `scripts/`, or is there a
   directory carved out that would let an untyped regression back in unnoticed?

10. **General doc-vs-code sweep.** Scan `CLAUDE.md`'s "Rules" section line by line against
    the pasted app code: for each rule stated as if it already holds (business logic in
    services, gettext on every user-facing string, idempotent tasks), name any file where the
    code does not actually match the rule, rather than assuming the rule is followed because
    it's written down.

## What NOT to flag

- The choice to store a report as one JSON document rather than a row per finding — documented
  and deliberate (`docs/decisions.md`, `docs/stack.md`).
- Absence of endpoints or models for the agent layer, connector, or generation features —
  not part of this phase.
- Style-only nits that `ruff`/`mypy --strict` would already catch mechanically — assume those
  gates run; focus on what a linter cannot see.

## Output format

Findings ranked by severity (data leak / silent data corruption first, then correctness,
then reliability, then hygiene). Each finding: file and function/line, the specific input or
timing that triggers it, which prior task (if any) it's a variant or regression of, and a
concrete fix — not "add more tests," but what the fix should actually do.
