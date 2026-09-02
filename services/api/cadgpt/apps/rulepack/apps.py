from __future__ import annotations

from django.apps import AppConfig


class RulePackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cadgpt.apps.rulepack"
    label = "rulepack"
    verbose_name = "Rule packs"
