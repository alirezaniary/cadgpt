"""Query logic lives in querysets, never in a view, a serializer, or a service body.

A service may call a queryset method; it may not assemble a filter itself. The point is
that every way of asking a question about a model is findable in one file, which is what
makes an N+1 or a missing tenant filter reviewable rather than scattered.
"""

from __future__ import annotations

from typing import Self, TypeVar, cast

from django.db import models

_T = TypeVar("_T", bound=models.Model)


class BaseQuerySet(models.QuerySet[_T]):
    """Shared query vocabulary."""

    def newest_first(self) -> Self:
        return self.order_by("-created_at", "-id")


class SoftDeleteQuerySet(BaseQuerySet[_T]):
    """Filtering for `SoftDeleteModelMixin`."""

    def alive(self) -> Self:
        return self.filter(deleted_at__isnull=True)

    def dead(self) -> Self:
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """The default manager for a soft-deleting model: hides removed rows.

    The default has to be the safe one. Code that forgets which view it wanted gets the
    one that cannot accidentally show a row somebody deleted.
    """

    def get_queryset(self) -> SoftDeleteQuerySet[models.Model]:
        return cast(SoftDeleteQuerySet[models.Model], super().get_queryset()).alive()


class DeletedManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """Only the removed rows, for restoring one or auditing what went."""

    def get_queryset(self) -> SoftDeleteQuerySet[models.Model]:
        return cast(SoftDeleteQuerySet[models.Model], super().get_queryset()).dead()


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):  # type: ignore[misc]
    """Every row, removed or not."""


class TenantScopedQuerySet(BaseQuerySet[_T]):
    """The isolation boundary, in the absence of database row-level security.

    Every read of a tenant-owned table goes through `for_tenant`. `TenantScopedViewSet`
    calls it on every request, and a contract test asserts that no viewset over a
    tenant-owned model escapes that base class -- because with a plain foreign key and no
    RLS, one forgotten filter is one firm reading another firm's unpublished drawings.

    `for_tenant(None)` returns nothing rather than everything. A bug that loses the tenant
    then shows up as an empty list, not as a cross-tenant leak.
    """

    def for_tenant(self, tenant: models.Model | None) -> Self:
        if tenant is None:
            return self.none()
        return self.filter(tenant=tenant)
