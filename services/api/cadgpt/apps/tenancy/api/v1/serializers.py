from __future__ import annotations

from typing import Any

from rest_framework import serializers

from cadgpt.apps.account.api.v1.serializers import UserSerializer
from cadgpt.apps.tenancy.choices import MembershipRole
from cadgpt.apps.tenancy.models import Membership, Tenant
from cadgpt.apps.tenancy.services import TenantProvisioningService


class TenantSerializer(serializers.ModelSerializer[Tenant]):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ("uuid", "name", "slug", "language", "timezone", "role", "created_at")
        read_only_fields = fields

    def get_role(self, obj: Tenant) -> str | None:
        """The requesting user's role here, annotated onto the queryset by the view."""
        return getattr(obj, "membership_role", None)


class TenantCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=63)
    language = serializers.ChoiceField(choices=["en", "fa"], default="en")

    def create(self, validated_data: dict[str, Any]) -> Tenant:
        return TenantProvisioningService().create(
            name=validated_data["name"],
            slug=validated_data["slug"],
            language=validated_data["language"],
            owner=self.context["request"].user,
        )

    def to_representation(self, instance: Tenant) -> dict[str, Any]:
        return TenantSerializer(instance).data


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ("uuid", "user", "role", "is_active", "created_at")
        read_only_fields = fields


class MembershipCreateSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=MembershipRole.choices, default=MembershipRole.MEMBER
    )

    def to_representation(self, instance: Membership) -> dict[str, Any]:
        return MembershipSerializer(instance).data
