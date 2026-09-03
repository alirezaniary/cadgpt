from __future__ import annotations

from typing import Any

from django.urls import reverse
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
    request the expensive one. `report_file_url` is cheap either way -- a link, not the
    file -- so it is on the summary too rather than gated behind the detail view.
    """

    duration_seconds = serializers.FloatField(read_only=True, allow_null=True)
    report_file_url = serializers.SerializerMethodField()

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
            "report_file_url",
            "created_at",
        )
        read_only_fields = fields

    def get_report_file_url(self, obj: CheckRun) -> str | None:
        """The authenticated download route, never the storage URL directly.

        T-0042 (queued, found by the T-0030 review) is exactly the mistake this avoids:
        serialising a `FileField` straight to a URL hands out a link nothing authenticates.
        This returns a path into `CheckRunViewSet.report_file`, which resolves through the
        same tenant-scoped `get_object()` as every other read on this viewset -- another
        tenant's run 404s rather than leaking a file.
        """
        if obj.report_file_id is None:
            return None
        return reverse(
            "review-v1:tenant-review-run-report-file",
            kwargs={"review_uuid": obj.review.uuid, "uuid": obj.uuid},
        )


class CheckRunDetailSerializer(CheckRunSummarySerializer):
    """One run with its full report, localized into the requesting user's language."""

    report = serializers.SerializerMethodField()

    class Meta(CheckRunSummarySerializer.Meta):
        fields: tuple[str, ...] = (
            *CheckRunSummarySerializer.Meta.fields,
            "report",
            "model_checksum",
            "rule_set_checksum",
            "rule_pack_selection",
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
        # `newest` came from `obj.runs.all()`, the reverse side of the FK it was fetched
        # through -- Django does not cache that direction, so `newest.review` would cost
        # its own query per row. `obj` already *is* that review, so set the cache by hand:
        # `report_file_url` (`CheckRunSummarySerializer.get_report_file_url`) reads
        # `.review.uuid`, and this is what keeps a page of reviews at a fixed query count.
        newest.review = obj
        return CheckRunSummarySerializer(newest).data


class ReviewCreateSerializer(serializers.Serializer[Any]):
    """References an uploaded model, and either a registered rule set or the catalogue.

    `rule_set` is optional: a review created without one has no rule source of its own,
    and each check against it must be given a catalogue selection when requested
    (`CheckRequestSerializer`, T-0031). Both `model_file` and `rule_set` are resolved
    through the tenant-scoped queryset rather than trusted from the payload, so naming
    another tenant's file is a 404 and not a leak.
    """

    name = serializers.CharField(max_length=255)
    model_file = serializers.UUIDField(write_only=True)
    rule_set = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    def create(self, validated_data: dict[str, Any]) -> Review:
        request = self.context["request"]

        media = (
            Media.objects.for_tenant(request.tenant)
            .filter(uuid=validated_data["model_file"])
            .first()
        )
        if media is None:
            raise NotFoundError(_("That uploaded model does not exist."))

        rule_set = None
        rule_set_uuid = validated_data.get("rule_set")
        if rule_set_uuid is not None:
            rule_set = (
                RuleSet.objects.for_tenant(request.tenant)
                .filter(uuid=rule_set_uuid)
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
    """Starting a check takes no input when the review names an uploaded rule set.

    `rule_packs` is the catalogue selection, required only when the review has none --
    `ReviewService.request_check` (`_resolve_selection`) is where that is enforced and
    where an unknown or ambiguous pack is refused, because that validation is business
    logic and belongs in the service, not here. This serializer only carries the raw
    input across the boundary.
    """

    rule_packs = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )

    def create(self, validated_data: dict[str, Any]) -> CheckRun:
        request = self.context["request"]
        return ReviewService(tenant=request.tenant).request_check(
            review=self.context["review"],
            requested_by=request.user,
            rule_pack_uuids=[str(uuid) for uuid in validated_data.get("rule_packs", [])],
        )

    def to_representation(self, instance: CheckRun) -> dict[str, Any]:
        return CheckRunSummarySerializer(instance).data
