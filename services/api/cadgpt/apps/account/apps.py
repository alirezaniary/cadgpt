from __future__ import annotations

from django.apps import AppConfig


class AccountConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadgpt.apps.account"
    label = "account"
    verbose_name = "Account"
