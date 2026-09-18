from __future__ import annotations

from django.apps import AppConfig


class InbrConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadgpt.apps.inbr"
    label = "inbr"
    verbose_name = "INBR corpus projection"
