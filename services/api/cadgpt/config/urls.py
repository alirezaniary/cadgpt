"""Root URL configuration.

It includes app-level URL modules and nothing else. Each app decides its own prefixes and
aggregates its own API versions, so adding a version or renaming a route is a change
inside one app rather than an edit here.
"""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.urls.resolvers import URLPattern, URLResolver

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("", include("cadgpt.apps.base.urls")),
    path("", include("cadgpt.apps.account.urls")),
    path("", include("cadgpt.apps.tenancy.urls")),
    path("", include("cadgpt.apps.project.urls")),
    path("", include("cadgpt.apps.media.urls")),
    path("", include("cadgpt.apps.rulepack.urls")),
    path("", include("cadgpt.apps.review.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
