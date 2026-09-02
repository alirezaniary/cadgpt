from __future__ import annotations

from typing import TYPE_CHECKING, Self

from cadgpt.apps.base.querysets import BaseQuerySet

if TYPE_CHECKING:
    # Imported for the quoted type parameter on the queryset below, which ruff
    # does not read as a use. Importing at runtime would be a cycle: the model
    # module imports the manager, which imports this one.
    from cadgpt.apps.tenancy.models import Membership, Tenant  # noqa: F401


class TenantQuerySet(BaseQuerySet["Tenant"]):
    def active(self) -> Self:
        return self.filter(is_active=True)

    def for_user(self, user_id: int) -> Self:
        return self.filter(
            memberships__user_id=user_id, memberships__is_active=True, is_active=True
        ).distinct()

    def by_slug(self, slug: str) -> Self:
        return self.filter(slug=slug)


class MembershipQuerySet(BaseQuerySet["Membership"]):
    def active(self) -> Self:
        return self.filter(is_active=True)

    def of_user(self, user_id: int) -> Self:
        return self.filter(user_id=user_id)

    def in_tenant(self, tenant_id: int) -> Self:
        return self.filter(tenant_id=tenant_id)

    def with_tenant(self) -> Self:
        return self.select_related("tenant")
