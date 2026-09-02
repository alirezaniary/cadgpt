from __future__ import annotations

from typing import Any

from rest_framework import mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from cadgpt.apps.rulepack.api.v1.filters import RuleSetFilterSet
from cadgpt.apps.rulepack.api.v1.serializers import (
    RuleSetCreateSerializer,
    RuleSetSerializer,
)
from cadgpt.apps.rulepack.models import RuleSet
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
