from __future__ import annotations

from typing import Any

from rest_framework import serializers

from cadgpt.apps.project.models import Project


class ProjectSerializer(serializers.ModelSerializer[Project]):
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ("uuid", "name", "review_count", "created_at")
        read_only_fields = fields

    def get_review_count(self, obj: Project) -> int:
        """Read from `ProjectViewSet.get_queryset`'s annotation when present, so the
        changelist costs one query for the whole page rather than one per row. Falls back
        to a live count for an instance that was never annotated -- the one
        `ProjectCreateSerializer` just created, which has no reviews yet regardless.
        """
        annotated = getattr(obj, "review_count", None)
        if annotated is not None:
            return int(annotated)
        return obj.reviews.count()


class ProjectCreateSerializer(serializers.Serializer[Any]):
    """`tenant` and `created_by` come from context, never from the payload -- the same
    pattern `ReviewCreateSerializer` and `RuleSetCreateSerializer` use.
    """

    name = serializers.CharField(max_length=255)

    def create(self, validated_data: dict[str, Any]) -> Project:
        request = self.context["request"]
        return Project.objects.create_project(
            tenant=request.tenant,
            name=validated_data["name"],
            created_by=request.user,
        )

    def to_representation(self, instance: Project) -> dict[str, Any]:
        return ProjectSerializer(instance).data
