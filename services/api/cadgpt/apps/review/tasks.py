"""Background work for reviews.

Named `<app>.<module>.<action>` explicitly, so a queued message stays routable when a
module moves. Every task here is idempotent, which `acks_late` makes a requirement rather
than a nicety: a message survives a worker that dies and will be delivered again.

The task body is deliberately three lines. Everything it does lives in a service, so the
same work is reachable from a management command, a test, and eventually an MCP tool,
without Celery in the way.
"""

from __future__ import annotations

from celery import shared_task

from cadgpt.apps.base.tasks import BaseTask
from cadgpt.apps.review.services.execution import CheckRunExecutor


@shared_task(
    base=BaseTask,
    name="review.tasks.execute_check_run",
    queue="checks",
    # A check is CPU-bound work over a large file. Retrying it because the model was
    # malformed would burn a worker five times to reach the same answer, so only the
    # transient failures BaseTask names are retried.
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3,
)
def execute_check_run(run_uuid: str) -> str:
    """Evaluate one check run to a terminal state. Safe to deliver twice."""
    run = CheckRunExecutor().execute(run_uuid)
    return run.status


@shared_task(
    base=BaseTask,
    name="review.tasks.reap_stalled_runs",
    queue="default",
)
def reap_stalled_runs() -> int:
    """Fail runs whose worker died, so a review is never blocked by a phantom check."""
    return CheckRunExecutor().reap_stalled()
