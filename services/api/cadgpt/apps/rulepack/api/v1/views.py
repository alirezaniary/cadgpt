from __future__ import annotations

from typing import Any

from rest_framework import mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from cadgpt.apps.base.drf.views import BaseViewSet
from cadgpt.apps.rulepack.api.v1.filters import RulePackFilterSet, RuleSetFilterSet
from cadgpt.apps.rulepack.api.v1.serializers import (
    RulePackSerializer,
    RuleSetCreateSerializer,
    RuleSetSerializer,
)
from cadgpt.apps.rulepack.models import RulePack, RuleSet
from cadgpt.apps.rulepack.services import RuleSetService
from cadgpt.apps.tenancy.drf.views import TenantScopedViewSet
from cadgpt.apps.tenancy.permissions import IsTenantMember, IsTenantMemberOrAbove


class RuleSetViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    TenantScopedViewSet,
):
    queryset = RuleSet.objects.all()
    permission_classes = (IsTenantMember,)
    filterset_class = RuleSetFilterSet
    ordering_fields = ("created_at", "name")
    ordering = ("-created_at",)

    serializer_classes = {  # noqa: RUF012
        "default": RuleSetSerializer,
        "create": RuleSetCreateSerializer,
    }
    queryset_selectors = {  # noqa: RUF012
        "list": ("source_file", "created_by"),
        "retrieve": ("source_file", "created_by"),
    }

    def get_permissions(self) -> list[Any]:
        if self.action in {"create", "destroy"}:
            return [IsTenantMemberOrAbove()]
        return list(super().get_permissions())

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.respond(serializer, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: RuleSet) -> None:
        RuleSetService(tenant=self.tenant).archive(rule_set=instance)


class RulePackViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, BaseViewSet):
    """The catalogue of rule packs we ship. Every tenant reads the same rows.

    Deliberately **not** a `TenantScopedViewSet`: `RulePack` owns no tenant data at all,
    so there is nothing to scope a read to. It inherits `BaseViewSet` directly, and the
    default `IsAuthenticated` permission is all that guards it -- no `X-Tenant` header is
    required, because a user browsing the catalogue may not have chosen a workspace yet
    (the same reasoning `TenantViewSet` documents for itself).

    Read-only by construction: only `ListModelMixin` and `RetrieveModelMixin` are mixed
    in, so create/update/delete are refused with 405 regardless of who asks. The
    catalogue is populated by `manage.py seed_rule_packs`, never by a request.

    `tests/test_tenant_isolation.py` names this viewset in `GLOBAL_CATALOGUE_VIEWSETS`
    and asserts its model never becomes tenant-owned -- that is what keeps this exemption
    from silently widening to cover a viewset that should have been scoped.
    """

    queryset = RulePack.objects.all()
    serializer_classes = {"default": RulePackSerializer}  # noqa: RUF012
    filterset_class = RulePackFilterSet
    ordering_fields = ("jurisdiction", "region", "version", "name", "created_at")
    ordering = ("jurisdiction", "region", "name", "version")
