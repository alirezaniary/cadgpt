from __future__ import annotations

from django.apps import AppConfig


class MediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadgpt.apps.media"
    label = "media"
    verbose_name = "Media"
