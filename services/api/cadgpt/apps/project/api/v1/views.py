from __future__ import annotations

from typing import Any, cast

from django.db.models import Count, QuerySet
from django.db.models.deletion import ProtectedError
from django.utils.translation import gettext_lazy as _
from rest_framework import mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from cadgpt.apps.base.exceptions import ConflictError
from cadgpt.apps.project.api.v1.serializers import (
    ProjectCreateSerializer,
    ProjectSerializer,
)
from cadgpt.apps.project.models import Project
from cadgpt.apps.tenancy.drf.views import TenantScopedViewSet
from cadgpt.apps.tenancy.permissions import IsTenantMember, IsTenantMemberOrAbove


class ProjectViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    TenantScopedViewSet,
):
    queryset = Project.objects.all()
    permission_classes = (IsTenantMember,)
    ordering_fields = ("created_at", "name")
    ordering = ("-created_at",)

    serializer_classes = {  # noqa: RUF012
        "default": ProjectSerializer,
        "create": ProjectCreateSerializer,
    }

    def get_queryset(self) -> QuerySet[Project]:
        """Annotated with the review count every row of the changelist needs, so it costs
        nothing beyond the one query the list view already makes."""
        return cast(
            "QuerySet[Project]",
            self.tenant_queryset().annotate(review_count=Count("reviews")),
        )

    def get_permissions(self) -> list[Any]:
        if self.action in {"create", "destroy"}:
            return [IsTenantMemberOrAbove()]
        return list(super().get_permissions())

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.respond(serializer, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Project) -> None:
        """A project with reviews under it is protected from deletion by
        `Review.project`'s `on_delete=PROTECT` -- the same reasoning as
        `Review.model_file`. There is no soft delete here to route around it with, so the
        database's own protection has to surface as an ordinary API error instead of an
        unhandled 500.
        """
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ConflictError(
                _("This project has reviews and cannot be deleted.")
            ) from exc
