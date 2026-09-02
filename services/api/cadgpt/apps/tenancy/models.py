"""The tenant, and the membership that lets someone reach it.

`TenantOwnedModel` is the abstract base every tenant-scoped table inherits. It declares
the foreign key by string reference rather than by import, so this module stays at its
layer and a model in a higher app can inherit it without an import cycle.

`tenant_related_name` on a subclass names the reverse accessor, so a tenant's related
managers read as `tenant.reviews` rather than `tenant.review_set`.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.models import UuidBaseModel
from cadgpt.apps.base.querysets import TenantScopedQuerySet
from cadgpt.apps.tenancy.choices import ROLE_RANK, MembershipRole
from cadgpt.apps.tenancy.repositories.custom_managers import (
    MembershipManager,
    TenantManager,
)

slug_validator = RegexValidator(
    regex=r"^[a-z0-9]+(-[a-z0-9]+)*$",
    message=_("A slug may contain lowercase letters, digits and single hyphens."),
)


class Tenant(UuidBaseModel):
    """One firm. The unit of isolation, billing, branding and configuration."""

    name = models.CharField(_("name"), max_length=255)
    slug = models.SlugField(
        _("slug"),
        max_length=63,
        unique=True,
        validators=[slug_validator, MinLengthValidator(2)],
        help_text=_("Identifies the tenant in URLs and in the tenant request header."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    #: Reports and notifications are written in this language unless a member overrides it.
    language = models.CharField(_("default language"), max_length=8, default="en")
    timezone = models.CharField(_("time zone"), max_length=64, default="UTC")

    objects: ClassVar[TenantManager] = TenantManager()

    class Meta:
        verbose_name = _("tenant")
        verbose_name_plural = _("tenants")
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Membership(UuidBaseModel):
    """A person's place in one tenant. The only thing that grants access to its data."""

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("tenant"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("user"),
    )
    role = models.CharField(
        _("role"),
        max_length=16,
        choices=MembershipRole.choices,
        default=MembershipRole.MEMBER,
    )
    is_active = models.BooleanField(_("active"), default=True)

    objects: ClassVar[MembershipManager] = MembershipManager()

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        constraints = (
            models.UniqueConstraint(
                fields=("tenant", "user"), name="unique_membership_per_tenant"
            ),
        )
        indexes = (models.Index(fields=("user", "is_active")),)

    def __str__(self) -> str:
        return f"{self.user} in {self.tenant} as {self.role}"

    def has_at_least(self, role: str) -> bool:
        """Rank comparison, so a role added later is ordered rather than enumerated."""
        return ROLE_RANK[self.role] >= ROLE_RANK[role]


class TenantOwnedModel(models.Model):
    """Every table holding tenant data inherits this. There is no other way in.

    The related name is declared per subclass through `tenant_related_name`, so each one
    states how it is reached from a tenant instead of relying on Django's default.
    """

    tenant_related_name = "%(class)ss"

    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        verbose_name=_("tenant"),
        db_index=True,
    )

    objects: ClassVar[TenantScopedQuerySet] = TenantScopedQuerySet.as_manager()  # type: ignore[type-arg,assignment]

    class Meta:
        abstract = True
