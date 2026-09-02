"""One serializer per action. Each declares only the fields its action needs."""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from cadgpt.apps.account.models import User
from cadgpt.apps.account.services import AccountService


class UserSerializer(serializers.ModelSerializer[User]):
    """The authenticated user's own record. Read-only; nothing here is a write path."""

    class Meta:
        model = User
        fields = ("uuid", "email", "full_name", "language", "created_at")
        read_only_fields = fields


class UserUpdateSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ("full_name", "language")


class RegisterSerializer(serializers.Serializer[Any]):
    """Registration delegates to `AccountService`; it does not create the user itself."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    full_name = serializers.CharField(required=False, allow_blank=True, default="")
    language = serializers.ChoiceField(choices=["en", "fa"], default="en")

    def create(self, validated_data: dict[str, Any]) -> User:
        return AccountService().register(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            language=validated_data.get("language", "en"),
        )

    def to_representation(self, instance: User) -> dict[str, Any]:
        return UserSerializer(instance).data


class ChangePasswordSerializer(serializers.Serializer[Any]):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        AccountService().change_password(
            user=instance,
            current_password=validated_data["current_password"],
            new_password=validated_data["new_password"],
        )
        return instance

    def to_representation(self, instance: User) -> dict[str, Any]:  # noqa: ARG002
        # The changed password is never echoed back, so the instance is unused here.
        return {"detail": str(_("The password was changed."))}


class LoginSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class TokenPairSerializer(serializers.Serializer[Any]):
    """What a successful login returns in the body.

    The refresh token is not here. It is set as an httpOnly cookie the browser will send
    back to the refresh endpoint and JavaScript cannot read, so a cross-site scripting
    flaw in the frontend cannot lift a credential that outlives the page.
    """

    access = serializers.CharField()
    expires_in = serializers.IntegerField()
    user = UserSerializer()
