"""A beat entry naming a task that does not exist fails silently at runtime, not at import.

Celery does not validate `CELERY_BEAT_SCHEDULE` against the task registry -- beat happily
sends a message for a name nothing answers to, and the failure only surfaces as
`NotRegistered` in worker logs. That is exactly the "review can be permanently stuck"
failure T-0084 closed, one layer up: a typo or a rename on either side of the string in
`settings/base.py` and `apps/review/tasks.py` reopens it with a green `make verify`. See
docs/tasks/T-0084-the-stalled-run-sweep-has-never-run-in-production.md.
"""

from __future__ import annotations

from django.conf import settings

from cadgpt.config.celery import app


def test_every_beat_scheduled_task_is_registered() -> None:
    # `app.autodiscover_tasks()` (celery.py) is lazy: without this, `app.tasks` only holds
    # whatever a task module happened to be imported already, which makes the assertion
    # below order-dependent on whatever else pytest collected first. A real worker never
    # hits that ambiguity -- `import_default_modules()` is what its own bootstep calls, so
    # calling it here reproduces the worker's actual discovery instead of guessing at it.
    app.loader.import_default_modules()
    scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
    assert scheduled, "CELERY_BEAT_SCHEDULE is empty -- nothing to check, update this test"
    assert scheduled <= app.tasks.keys()
