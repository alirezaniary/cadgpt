"""Reviews, and the runs beneath them.

Runs are nested under their review, because a run has no meaning apart from one: its
identity is "this model against these rules, at this time". A flat `/runs/` collection
would invite reading one without knowing what it checked.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import QuerySet
from django.http import FileResponse
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from cadgpt.apps.base.exceptions import NotFoundError
from cadgpt.apps.review.api.v1.filters import CheckRunFilterSet, ReviewFilterSet
from cadgpt.apps.review.api.v1.serializers import (
    CheckRequestSerializer,
    CheckRunDetailSerializer,
    CheckRunSummarySerializer,
    ReviewCreateSerializer,
    ReviewSerializer,
)
from cadgpt.apps.review.models import CheckRun, Review
from cadgpt.apps.tenancy.drf.views import TenantScopedViewSet
from cadgpt.apps.tenancy.permissions import IsTenantMember, IsTenantMemberOrAbove


class ReviewViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    TenantScopedViewSet,
):
    queryset = Review.objects.all()
    permission_classes = (IsTenantMember,)
    filterset_class = ReviewFilterSet
    ordering_fields = ("created_at", "name")
    ordering = ("-created_at",)

    serializer_classes = {  # noqa: RUF012
        "default": ReviewSerializer,
        "create": ReviewCreateSerializer,
        "check": CheckRequestSerializer,
    }

    def get_queryset(self) -> QuerySet[Review]:
        """One prefetch for the runs, so a page of reviews is a fixed query count."""
        return cast(
            "QuerySet[Review]", self.tenant_queryset().with_inputs().with_latest_run()
        )

    def get_permissions(self) -> list[Any]:
        if self.action in {"create", "destroy", "check"}:
            return [IsTenantMemberOrAbove()]
        return list(super().get_permissions())

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.respond(serializer, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=CheckRequestSerializer, responses={202: CheckRunSummarySerializer}
    )
    @action(detail=True, methods=["post"], throttle_classes=[])
    def check(self, request: Request, uuid: str) -> Response:  # noqa: ARG002
        """Queue a check of this review. Returns immediately with the run to poll.

        202, not 200: the work has been accepted, not done. A model of any real size takes
        seconds to minutes, which is past what a browser or a proxy will hold open.

        The body is optional and, until T-0031, was always empty: a review with its own
        `rule_set` still needs nothing here. It carries `rule_packs` -- the catalogue
        selection -- only for a review with no `rule_set` of its own.
        """
        review = self.get_object()
        serializer = self.get_serializer(
            data=request.data, context={**self.get_serializer_context(), "review": review}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.respond(serializer, status=status.HTTP_202_ACCEPTED)


class CheckRunViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantScopedViewSet
):
    """Runs of one review, addressed as `/reviews/{uuid}/runs/`."""

    queryset = CheckRun.objects.all()
    permission_classes = (IsTenantMember,)
    filterset_class = CheckRunFilterSet
    ordering_fields = ("created_at",)
    ordering = ("-created_at",)

    serializer_classes = {  # noqa: RUF012
        "default": CheckRunSummarySerializer,
        "list": CheckRunSummarySerializer,
        "retrieve": CheckRunDetailSerializer,
    }

    def get_queryset(self) -> QuerySet[CheckRun]:
        runs = self.tenant_queryset().filter(review__uuid=self.kwargs["review_uuid"])
        if self.action == "list":
            # The report is deferred rather than excluded: a list of runs must never
            # load a page of multi-megabyte documents to render six numbers.
            # `select_related("review")` keeps `report_file_url`
            # (`CheckRunSummarySerializer.get_report_file_url`, which reads
            # `.review.uuid`) at one query for the page rather than one per row.
            return cast(
                "QuerySet[CheckRun]", runs.without_report().select_related("review")
            )
        return cast("QuerySet[CheckRun]", runs.with_inputs())

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="report-file", throttle_classes=[])
    def report_file(self, request: Request, review_uuid: str, uuid: str) -> FileResponse:  # noqa: ARG002
        """Stream the generated Markdown report, authenticated and tenant-scoped.

        `get_object()` narrows through `get_queryset()` above -- `for_tenant(self.tenant)`
        composed with this review's uuid -- exactly like `retrieve`, so another tenant's
        run 404s rather than handing out a bare storage URL the way `RulePackSerializer.
        source_file` does today (`docs/tasks/T-0042-the-catalogue-hands-out-a-storage-url.
        md`, queued rather than fixed there because the catalogue is deliberately global;
        a generated report is tenant data, and this route is what keeps it authenticated).
        Not routed through `BaseViewSet.respond()`: that wraps a serializer's JSON body,
        and a file has none to wrap.
        """
        run = self.get_object()
        if run.report_file_id is None:
            raise NotFoundError(_("This run has no generated report file yet."))
        return FileResponse(
            run.report_file.file.open("rb"),
            as_attachment=True,
            filename=run.report_file.original_name,
            content_type=run.report_file.content_type or "text/markdown",
        )
