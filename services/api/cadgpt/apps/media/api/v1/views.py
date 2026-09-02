from __future__ import annotations

from typing import Any

from rest_framework import mixins, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from cadgpt.apps.media.api.v1.filters import MediaFilterSet
from cadgpt.apps.media.api.v1.serializers import MediaSerializer, MediaUploadSerializer
from cadgpt.apps.media.models import Media
from cadgpt.apps.tenancy.drf.views import TenantScopedViewSet
from cadgpt.apps.tenancy.permissions import IsTenantMember, IsTenantMemberOrAbove


class MediaViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    TenantScopedViewSet,
):
    """Uploads, scoped to the tenant named by the request."""

    queryset = Media.objects.all()
    permission_classes = (IsTenantMember,)
    parser_classes = (MultiPartParser, FormParser)
    filterset_class = MediaFilterSet
    ordering_fields = ("created_at", "size_bytes")
    ordering = ("-created_at",)

    serializer_classes = {  # noqa: RUF012
        "default": MediaSerializer,
        "create": MediaUploadSerializer,
    }
    queryset_selectors = {  # noqa: RUF012
        "list": ("uploaded_by",),
        "retrieve": ("uploaded_by",),
    }

    def get_permissions(self) -> list[Any]:
        if self.action == "create":
            return [IsTenantMemberOrAbove()]
        return list(super().get_permissions())

    def get_throttles(self) -> list[Any]:
        if self.action == "create":
            self.throttle_scope = "upload"
        return super().get_throttles()

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.respond(serializer, status=status.HTTP_201_CREATED)
