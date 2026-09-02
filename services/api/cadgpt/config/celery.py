"""The Celery application.

Tasks are named explicitly as `<app>.<module>.<action>` rather than by module path, so a
queued message stays routable when a module moves. Every task inherits
`cadgpt.apps.base.tasks.BaseTask`, which supplies the retry and logging behaviour, and
every task must be safe to run twice: `acks_late` means a message survives a dead worker
and will be delivered again.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cadgpt.config.settings.production")

app = Celery("cadgpt")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
