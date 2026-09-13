from __future__ import annotations

from typing import Any

from rest_framework import serializers

from cadgpt.apps.media.choices import UPLOADABLE_KINDS
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
    # `UPLOADABLE_KINDS`, not `MediaKind.choices`: `report` is a real `MediaKind` but is
    # written only by `ReportGenerationService.generate`, never received from a client
    # (T-0054) -- restricting the field is what makes that comment on `MediaKind.REPORT`
    # true rather than aspirational.
    kind = serializers.ChoiceField(
        choices=[(kind.value, kind.label) for kind in UPLOADABLE_KINDS]
    )

    def create(self, validated_data: dict[str, Any]) -> Media:
        request = self.context["request"]
        return MediaService(tenant=request.tenant).store(
            upload=validated_data["file"],
            kind=validated_data["kind"],
            uploaded_by=request.user,
        )

    def to_representation(self, instance: Media) -> dict[str, Any]:
        return MediaSerializer(instance).data
