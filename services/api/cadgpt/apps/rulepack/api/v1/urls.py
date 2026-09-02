from __future__ import annotations

from django.urls import include, path

from cadgpt.apps.base.drf.routers import ScopedRouter
from cadgpt.apps.rulepack.api.v1.views import RulePackViewSet, RuleSetViewSet

app_name = "rulepack-v1"

router = ScopedRouter(scope="tenant")
router.register("rule-sets", RuleSetViewSet, basename="rule-set")
router.register("rule-packs", RulePackViewSet, basename="rule-pack")

urlpatterns = [path("", include(router.urls))]
