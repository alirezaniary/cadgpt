"""A rule set: one IDS file a tenant checks models against, kept so it can be reused.

The workflow is check, fix, re-check, and against many models. Re-uploading the same rules
each time would make two runs incomparable and would lose the fact that they were the same
rules. A stored rule set is what makes a run reproducible from its inputs.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.models import SoftDeleteModelMixin, UuidBaseModel
from cadgpt.apps.rulepack.repositories.custom_managers import (
    AllRuleSetManager,
    DeletedRuleSetManager,
    RuleSetManager,
)
from cadgpt.apps.tenancy.models import TenantOwnedModel


class RuleSet(TenantOwnedModel, SoftDeleteModelMixin, UuidBaseModel):
    """A named, validated IDS file.

    Soft-deleted rather than removed: a rule set referenced by a completed check run is
    the only record of what that run actually checked, so deleting it would make an
    existing report unexplainable.
    """

    tenant_related_name = "rule_sets"

    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)

    source_file = models.ForeignKey(
        "media.Media",
        on_delete=models.PROTECT,
        related_name="rule_sets",
        verbose_name=_("source file"),
    )

    # Read out of the IDS at upload time, so a list view never has to parse XML.
    title = models.CharField(_("declared title"), max_length=255, blank=True)
    author = models.CharField(_("declared author"), max_length=255, blank=True)
    version = models.CharField(_("declared version"), max_length=64, blank=True)
    specification_count = models.PositiveIntegerField(_("specifications"), default=0)

    created_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_rule_sets",
        verbose_name=_("created by"),
    )

    objects: ClassVar[RuleSetManager] = RuleSetManager()
    objects_deleted: ClassVar[DeletedRuleSetManager] = DeletedRuleSetManager()
    objects_with_deleted: ClassVar[AllRuleSetManager] = AllRuleSetManager()

    class Meta:
        verbose_name = _("rule set")
        verbose_name_plural = _("rule sets")
        ordering = ("-created_at",)
        constraints = (
            models.UniqueConstraint(
                fields=("tenant", "name"),
                condition=models.Q(deleted_at__isnull=True),
                name="unique_active_rule_set_name_per_tenant",
            ),
        )

    def __str__(self) -> str:
        return self.name
