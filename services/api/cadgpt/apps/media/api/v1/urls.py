from __future__ import annotations

from django.urls import include, path

from cadgpt.apps.base.drf.routers import ScopedRouter
from cadgpt.apps.media.api.v1.views import MediaViewSet

app_name = "media-v1"

router = ScopedRouter(scope="tenant")
router.register("media", MediaViewSet, basename="media")

urlpatterns = [path("", include(router.urls))]
