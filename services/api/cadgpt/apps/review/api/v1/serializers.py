from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.media.api.v1.serializers import MediaSerializer
from cadgpt.apps.media.models import Media
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.review.services import ReviewService, localize_report
from cadgpt.apps.rulepack.api.v1.serializers import RuleSetSerializer
from cadgpt.apps.rulepack.models import RuleSet


class CheckRunSummarySerializer(serializers.ModelSerializer[CheckRun]):
    """A run without its report. What a list of runs shows.

    The report document can be megabytes; sending it in a list would make the common
    request the expensive one.
    """

    duration_seconds = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = CheckRun
        fields: tuple[str, ...] = (
            "uuid",
            "status",
            "outcome",
            "engine_version",
            "specifications_passed",
            "specifications_failed",
            "specifications_indeterminate",
            "passed",
            "failed",
            "indeterminate",
            "failure_reason",
            "failure_detail",
            "queued_at",
            "started_at",
            "finished_at",
            "duration_seconds",
            "created_at",
        )
        read_only_fields = fields


class CheckRunDetailSerializer(CheckRunSummarySerializer):
    """One run with its full report, localized into the requesting user's language."""

    report = serializers.SerializerMethodField()

    class Meta(CheckRunSummarySerializer.Meta):
        fields: tuple[str, ...] = (
            *CheckRunSummarySerializer.Meta.fields,
            "report",
            "model_checksum",
            "rule_set_checksum",
        )
        read_only_fields = fields

    def get_report(self, obj: CheckRun) -> dict[str, Any] | None:
        return localize_report(obj.report)


class ReviewSerializer(serializers.ModelSerializer[Review]):
    model_file = MediaSerializer(read_only=True)
    rule_set = RuleSetSerializer(read_only=True)
    latest_run = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "uuid",
            "name",
            "model_file",
            "rule_set",
            "latest_run",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_latest_run(self, obj: Review) -> dict[str, Any] | None:
        """Read from the prefetched runs, so a list of reviews costs two queries."""
        runs = list(obj.runs.all())
        if not runs:
            return None
        newest = max(runs, key=lambda run: run.created_at)
        return CheckRunSummarySerializer(newest).data


class ReviewCreateSerializer(serializers.Serializer[Any]):
    """References an uploaded model and a registered rule set by UUID.

    Both are resolved through the tenant-scoped queryset rather than trusted from the
    payload, so naming another tenant's file is a 404 and not a leak.
    """

    name = serializers.CharField(max_length=255)
    model_file = serializers.UUIDField(write_only=True)
    rule_set = serializers.UUIDField(write_only=True)

    def create(self, validated_data: dict[str, Any]) -> Review:
        request = self.context["request"]

        media = (
            Media.objects.for_tenant(request.tenant)
            .filter(uuid=validated_data["model_file"])
            .first()
        )
        if media is None:
            raise NotFoundError(_("That uploaded model does not exist."))

        rule_set = (
            RuleSet.objects.for_tenant(request.tenant)
            .filter(uuid=validated_data["rule_set"])
            .first()
        )
        if rule_set is None:
            raise NotFoundError(_("That rule set does not exist."))

        return ReviewService(tenant=request.tenant).create(
            name=validated_data["name"],
            model_file=media,
            rule_set=rule_set,
            created_by=request.user,
        )

    def to_representation(self, instance: Review) -> dict[str, Any]:
        return ReviewSerializer(instance).data


class CheckRequestSerializer(serializers.Serializer[Any]):
    """Starting a check takes no input; the review already names its own inputs."""

    def create(self, validated_data: dict[str, Any]) -> CheckRun:  # noqa: ARG002
        request = self.context["request"]
        return ReviewService(tenant=request.tenant).request_check(
            review=self.context["review"], requested_by=request.user
        )

    def to_representation(self, instance: CheckRun) -> dict[str, Any]:
        return CheckRunSummarySerializer(instance).data
