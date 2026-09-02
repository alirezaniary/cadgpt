"""Operational endpoints and the API schema. No domain resources are routed here."""

from __future__ import annotations

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from cadgpt.apps.base.views import healthz, readyz

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
