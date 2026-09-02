"""Aggregates this app's API versions. Versions are added here, never in config/urls."""

from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("v1/", include("cadgpt.apps.account.api.v1.urls")),
]
