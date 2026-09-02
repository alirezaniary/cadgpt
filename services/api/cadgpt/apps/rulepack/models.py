"""A rule set: one IDS file a tenant checks models against, kept so it can be reused.

The workflow is check, fix, re-check, and against many models. Re-uploading the same rules
each time would make two runs incomparable and would lose the fact that they were the same
rules. A stored rule set is what makes a run reproducible from its inputs.
"""

from __future__ import annotations

import uuid as uuid_lib
from pathlib import PurePosixPath
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.models import SoftDeleteModelMixin, UuidBaseModel
from cadgpt.apps.rulepack.repositories.custom_managers import (
    AllRuleSetManager,
    DeletedRuleSetManager,
    RulePackManager,
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


def rule_pack_upload_to(instance: RulePack, filename: str) -> str:
    """Partition storage by jurisdiction, then by pack. Never by tenant: a shipped pack
    belongs to no tenant, so its file lives outside `media.Media`'s tenant-partitioned
    tree entirely rather than under a `tenants/<uuid>/` prefix that would misstate it as
    one tenant's upload.
    """
    suffix = PurePosixPath(filename).suffix.lower()[:16]
    return f"rule-packs/{instance.jurisdiction}/{uuid_lib.uuid4()}{suffix}"


class RulePack(UuidBaseModel):
    """A rule pack we ship: an IDS file scoped to a jurisdiction, region and version.

    Deliberately **not** `TenantOwnedModel`. `RuleSet` above is the right model for an
    IDS an office authored and uploaded -- it belongs to exactly one tenant. A pack we
    publish belongs to none of them: every tenant selects from the same catalogue, and
    the tempting shortcut of making `RuleSet.tenant` nullable to hold both cases was
    refused (`docs/decisions.md`, `docs/plan.md` Phase 3) because it would put a nullable
    column at the centre of the one structurally-enforced invariant in this codebase --
    `for_tenant` stays total, and this table simply carries no `tenant` column for it to
    be called on.

    That is also the declaration `tests/test_tenant_isolation.py` reads: a viewset over
    this model is legal without inheriting `TenantScopedViewSet` only because, and only
    for as long as, this model does not inherit `TenantOwnedModel`. See
    `GLOBAL_CATALOGUE_VIEWSETS` and the test built on it in that module.

    Carries a source citation because `prd.md` §5.7 requires every finding to carry
    attribution, and a pack shipped under our name is asserting something -- unlike an
    office's own upload, which asserts nothing beyond what the office typed.
    """

    name = models.CharField(_("name"), max_length=255)
    description = models.TextField(_("description"), blank=True)

    jurisdiction = models.CharField(_("jurisdiction"), max_length=64)
    region = models.CharField(_("region"), max_length=64, blank=True)
    version = models.CharField(_("pack version"), max_length=64)

    source_file = models.FileField(
        _("source file"), upload_to=rule_pack_upload_to, max_length=512
    )

    #: Where this pack came from and who published it. Required, not inferred: a pack we
    #: ship is an assertion under our name, and an unattributed one is not publishable.
    source_citation = models.TextField(_("source citation"))

    # Read out of the IDS at seed time, mirroring RuleSet's fields of the same name.
    title = models.CharField(_("declared title"), max_length=255, blank=True)
    author = models.CharField(_("declared author"), max_length=255, blank=True)
    specification_count = models.PositiveIntegerField(_("specifications"), default=0)

    objects: ClassVar[RulePackManager] = RulePackManager()

    class Meta:
        verbose_name = _("rule pack")
        verbose_name_plural = _("rule packs")
        ordering = ("jurisdiction", "region", "name", "version")
        constraints = (
            models.UniqueConstraint(
                fields=("jurisdiction", "region", "version", "name"),
                name="unique_rule_pack_identity",
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.jurisdiction}, {self.version})"
