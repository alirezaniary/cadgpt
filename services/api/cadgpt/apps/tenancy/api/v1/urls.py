from __future__ import annotations

from django.urls import include, path

from cadgpt.apps.base.drf.routers import ScopedRouter
from cadgpt.apps.tenancy.api.v1.views import MembershipViewSet, TenantViewSet

app_name = "tenancy-v1"

router = ScopedRouter(scope="tenant")
router.register("tenants", TenantViewSet, basename="tenant")
router.register("members", MembershipViewSet, basename="membership")

urlpatterns = [path("", include(router.urls))]
