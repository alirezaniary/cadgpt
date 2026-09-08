"""The base every Celery task inherits.

Four things it supplies, so no task has to remember them.

**A retry policy that is explicit.** `autoretry_for` names which exceptions are worth
retrying; anything else fails immediately and loudly rather than being attempted twenty
times. Backoff is exponential with jitter, so a downstream outage does not get a
synchronized retry storm on recovery.

**Logging around every attempt**, bound to the task name and id, including the failure.

**A statement of the contract:** with `acks_late` set, a message survives a worker that
dies mid-task and is delivered again. Every task must therefore be idempotent -- running
it twice must produce the same end state as running it once. That is a property of the
task body, which this class cannot enforce; what it can do is make the requirement
unavoidable to read.

**The active language.** A Celery task has no HTTP request and therefore no
`Accept-Language` header -- `LocaleMiddleware` never runs for it, so any `gettext` call a
task body makes (directly, or through a service it calls) would otherwise translate
against whatever the current thread happens to have active, which for a fresh worker
thread that never called `translation.activate()` falls back to `settings.LANGUAGE_CODE`
by accident of Django's own fallback rather than by anything this product decided on
purpose. `__call__` activates `settings.LANGUAGE_CODE` explicitly around every task body,
for every task that inherits this class, so that stays true by construction instead of by
nobody else in the process ever calling `activate()` first. `translation.override` is a
context manager: a task body that needs a different language for part of its own work
(`ReportGenerationService.generate` overrides to the tenant's own `language`, so a
tenant that chose "en" still gets an English report) nests cleanly inside it and restores
this default on exit. See `docs/tasks/
T-0083-the-hardcoded-persian-product-is-not-hardcoded.md`.
"""

from __future__ import annotations

from typing import Any

import structlog
from celery import Task
from django.conf import settings
from django.utils import translation

log = structlog.get_logger(__name__)


class BaseTask(Task):
    """Shared retry, logging and language-activation behaviour. Subclasses must be
    idempotent."""

    autoretry_for: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)
    max_retries = 5
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    acks_late = True
    reject_on_worker_lost = True
    track_started = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        bound = log.bind(task=self.name, task_id=getattr(self.request, "id", None))
        bound.info("task_started")
        with translation.override(settings.LANGUAGE_CODE):
            result = super().__call__(*args, **kwargs)
        bound.info("task_finished")
        return result

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        log.bind(task=self.name, task_id=task_id).error(
            "task_failed", error=str(exc), error_type=type(exc).__name__
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)
