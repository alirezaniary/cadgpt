from __future__ import annotations

from django.apps import AppConfig
from django.conf import settings


class BaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadgpt.apps.base"
    label = "base"
    verbose_name = "Base"

    def ready(self) -> None:
        from cadgpt.apps.base import logging as app_logging

        app_logging.configure(json_output=not settings.DEBUG)
