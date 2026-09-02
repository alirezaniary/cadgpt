from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.media.api.v1.serializers import MediaSerializer
from cadgpt.apps.media.models import Media
from cadgpt.apps.rulepack.models import RuleSet
from cadgpt.apps.rulepack.services import RuleSetService


class RuleSetSerializer(serializers.ModelSerializer[RuleSet]):
    source_file = MediaSerializer(read_only=True)

    class Meta:
        model = RuleSet
        fields = (
            "uuid",
            "name",
            "description",
            "title",
            "author",
            "version",
            "specification_count",
            "source_file",
            "created_at",
        )
        read_only_fields = fields


class RuleSetCreateSerializer(serializers.Serializer[Any]):
    """Takes an already-uploaded file by UUID, not the bytes.

    Upload and registration are separate steps so a large upload is never repeated because
    a name collided, and so the file is resolved through the tenant-scoped media queryset
    rather than trusted from the request.
    """

    source_file = serializers.UUIDField(write_only=True)
    name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def create(self, validated_data: dict[str, Any]) -> RuleSet:
        request = self.context["request"]
        media = (
            Media.objects.for_tenant(request.tenant)
            .filter(uuid=validated_data["source_file"])
            .first()
        )
        if media is None:
            raise NotFoundError(_("That uploaded file does not exist."))

        return RuleSetService(tenant=request.tenant).create(
            source_file=media,
            name=validated_data.get("name", ""),
            description=validated_data.get("description", ""),
            created_by=request.user,
        )

    def to_representation(self, instance: RuleSet) -> dict[str, Any]:
        return RuleSetSerializer(instance).data
