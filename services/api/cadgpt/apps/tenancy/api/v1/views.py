"""Workspaces the caller belongs to, and who else is in them."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import F, QuerySet
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from cadgpt.apps.account.models import User
from cadgpt.apps.base.drf.views import BaseViewSet
from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.tenancy.api.v1.serializers import (
    MembershipCreateSerializer,
    MembershipSerializer,
    TenantCreateSerializer,
    TenantSerializer,
)
from cadgpt.apps.tenancy.models import Membership, Tenant
from cadgpt.apps.tenancy.permissions import IsTenantAdmin, IsTenantMember
from cadgpt.apps.tenancy.resolution import current_tenant, resolve_membership
from cadgpt.apps.tenancy.services import MembershipService


class TenantViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, BaseViewSet
):
    """The workspaces this user can act in.

    Not tenant-scoped: this is the endpoint a client calls *before* it knows which tenant
    to name, so it is scoped by membership instead.
    """

    queryset = Tenant.objects.all()
    serializer_classes = {  # noqa: RUF012 - DRF reads this off the class
        "default": TenantSerializer,
        "create": TenantCreateSerializer,
    }

    def get_queryset(self) -> QuerySet[Tenant]:
        return cast(
            "QuerySet[Tenant]",
            Tenant.objects.for_user(self.request.user.pk)
            .annotate(membership_role=F("memberships__role"))
            .order_by("name"),
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.respond(serializer, status=status.HTTP_201_CREATED)


class MembershipViewSet(mixins.ListModelMixin, BaseViewSet):
    """Members of the tenant named by the request header."""

    queryset = Membership.objects.all()
    permission_classes = (IsTenantMember,)
    serializer_classes = {  # noqa: RUF012
        "default": MembershipSerializer,
        "invite": MembershipCreateSerializer,
        "revoke": MembershipSerializer,
    }

    def get_queryset(self) -> QuerySet[Membership]:
        tenant = current_tenant(self.request)
        if tenant is None:
            return cast("QuerySet[Membership]", Membership.objects.none())
        return cast(
            "QuerySet[Membership]",
            Membership.objects.in_tenant(tenant.pk)
            .select_related("user")
            .order_by("-created_at"),
        )

    @action(detail=False, methods=["post"], permission_classes=(IsTenantAdmin,))
    def invite(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.by_email(serializer.validated_data["email"]).first()
        if user is None:
            raise NotFoundError(_("No account exists for that email address."))

        actor = resolve_membership(request)
        assert actor is not None  # IsTenantAdmin already established this
        membership = MembershipService(tenant=actor.tenant).add(
            user=user,
            role=serializer.validated_data["role"],
            actor_membership=actor,
        )
        return Response(
            MembershipSerializer(membership).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], permission_classes=(IsTenantAdmin,))
    def revoke(self, request: Request, uuid: str) -> Response:
        actor = resolve_membership(request)
        assert actor is not None  # IsTenantAdmin already established this
        MembershipService(tenant=actor.tenant).revoke(
            membership_uuid=uuid, actor_membership=actor
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
