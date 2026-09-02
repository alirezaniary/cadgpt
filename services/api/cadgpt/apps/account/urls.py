"""App-level aggregator, included by the root URLconf."""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("api/", include("cadgpt.apps.account.api.urls")),
]
