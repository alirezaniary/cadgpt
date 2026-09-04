from __future__ import annotations

from django.urls import include, path

from cadgpt.apps.base.drf.routers import ScopedRouter
from cadgpt.apps.project.api.v1.views import ProjectViewSet

app_name = "project-v1"

router = ScopedRouter(scope="tenant")
router.register("projects", ProjectViewSet, basename="project")

urlpatterns = [path("", include(router.urls))]
