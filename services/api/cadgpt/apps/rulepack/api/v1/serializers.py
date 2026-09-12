from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.media.api.v1.serializers import MediaSerializer
from cadgpt.apps.media.models import Media
from cadgpt.apps.rulepack.models import RulePack, RuleSet
from cadgpt.apps.rulepack.services import RuleSetService


class RulePackSerializer(serializers.ModelSerializer[RulePack]):
    """Read-only: the catalogue is written by `manage.py seed_rule_packs`, never by a
    request. See `RulePackViewSet`.

    Deliberately omits `source_file` (T-0042): it is a `FileField`, and DRF serialises a
    `FileField` to its storage URL. `MediaSerializer` already refuses to hand out a raw
    file URL for the same reason; nothing in this codebase consumes a rule pack's IDS
    bytes through the catalogue API -- a selected pack's IDS is read from disk by the
    check task itself (`cadgpt.apps.review.services`), never fetched over HTTP -- so
    there is no authenticated download to route this through either. A pack is
    identified by its metadata alone.
    """

    class Meta:
        model = RulePack
        fields = (
            "uuid",
            "name",
            "description",
            "jurisdiction",
            "region",
            "version",
            "title",
            "author",
            "specification_count",
            "source_citation",
            "created_at",
        )
        read_only_fields = fields


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
