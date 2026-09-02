"""Project configuration.

Importing the Celery application here is what makes `@shared_task` bind to it when Django
starts, whether the process is a web worker, a Celery worker, or a management command.
"""

from __future__ import annotations

from cadgpt.config.celery import app as celery_app

__all__ = ["celery_app"]
