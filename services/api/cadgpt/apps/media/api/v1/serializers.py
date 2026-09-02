from __future__ import annotations

from typing import Any

from rest_framework import serializers

from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.media.services import MediaService


class MediaSerializer(serializers.ModelSerializer[Media]):
    class Meta:
        model = Media
        fields = (
            "uuid",
            "kind",
            "original_name",
            "content_type",
            "size_bytes",
            "checksum_sha256",
            "created_at",
        )
        read_only_fields = fields


class MediaUploadSerializer(serializers.Serializer[Any]):
    """Accepts the file and delegates storage; it does not write anything itself."""

    file = serializers.FileField(write_only=True)
    kind = serializers.ChoiceField(choices=MediaKind.choices)

    def create(self, validated_data: dict[str, Any]) -> Media:
        request = self.context["request"]
        return MediaService(tenant=request.tenant).store(
            upload=validated_data["file"],
            kind=validated_data["kind"],
            uploaded_by=request.user,
        )

    def to_representation(self, instance: Media) -> dict[str, Any]:
        return MediaSerializer(instance).data
