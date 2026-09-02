"""Thin write wrappers. Everything they take has already been decided by a service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import Manager
from django.utils.text import slugify

from cadgpt.apps.tenancy.repositories.querysets import MembershipQuerySet, TenantQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.tenancy.models import Membership, Tenant


class TenantManager(Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    def create_tenant(self, *, name: str, slug: str, language: str = "en") -> Tenant:
        tenant = self.model(name=name.strip(), slug=slugify(slug), language=language)
        tenant.full_clean()
        tenant.save(using=self._db)
        return cast("Tenant", tenant)


class MembershipManager(Manager.from_queryset(MembershipQuerySet)):  # type: ignore[misc]
    def grant(self, *, tenant: Any, user: Any, role: str) -> Membership:
        membership = self.model(tenant=tenant, user=user, role=role)
        membership.full_clean()
        membership.save(using=self._db)
        return cast("Membership", membership)
