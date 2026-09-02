from __future__ import annotations

from django.urls import include, path

urlpatterns = [path("v1/", include("cadgpt.apps.media.api.v1.urls"))]
