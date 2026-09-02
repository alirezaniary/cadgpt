"""The guard that stands in for database row-level security.

It lives above every app rather than inside one, because it inspects all of them: the
import contract that keeps `tenancy` from reaching into `review` is exactly what a test
spanning both must not violate. An architecture test belongs at the level whose
architecture it describes.

Isolation here is a foreign key and a scoped queryset, which means it holds only as long
as every viewset over a tenant-owned table actually applies the scope. That is a property
of the code, so it is checked as one: this module walks every registered route and every
model in the project and fails the build when one escapes.

A reviewer noticing a missing filter is not a control. This is.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.apps import apps
from django.urls import get_resolver
from rest_framework.test import APIClient

from cadgpt.apps.base.querysets import TenantScopedQuerySet
from cadgpt.apps.media.models import Media
from cadgpt.apps.review.models import Review
from cadgpt.apps.rulepack.models import RuleSet
from cadgpt.apps.tenancy.drf.views import TenantScopedViewSet
from cadgpt.apps.tenancy.models import Tenant, TenantOwnedModel

#: Viewsets that read a tenant-owned model but are deliberately scoped some other way.
#: Each needs a reason, and each is covered by a behavioural test of its own.
SCOPED_BY_MEMBERSHIP = {
    # Lists the workspaces a user may act in, so it runs before a tenant is chosen and is
    # scoped by membership instead. Covered by test_tenant_viewset_lists_only_own_tenants.
    "TenantViewSet",
    # Members of the tenant in the request header, scoped explicitly in get_queryset.
    "MembershipViewSet",
}


def _registered_viewsets() -> dict[str, type[Any]]:
    """Every viewset class reachable through the project's URL configuration."""
    found: dict[str, type[Any]] = {}

    def walk(resolver: Any) -> None:
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern)
                continue
            cls = getattr(pattern.callback, "cls", None)
            if cls is not None and hasattr(cls, "queryset"):
                found[cls.__name__] = cls

    walk(get_resolver())
    return found


def _tenant_owned_models() -> list[type[Any]]:
    return [
        model
        for model in apps.get_models()
        if issubclass(model, TenantOwnedModel) and not model._meta.abstract
    ]


def test_every_tenant_owned_model_is_reachable_only_through_a_scoped_queryset() -> None:
    """An unscoped default manager on a tenant table is a leak waiting to happen."""
    unscoped = [
        model.__name__
        for model in _tenant_owned_models()
        if not isinstance(model._default_manager.get_queryset(), TenantScopedQuerySet)
    ]
    assert unscoped == [], (
        "these tenant-owned models have a default manager that is not tenant-scoped, so "
        "an ordinary .objects.filter() would read every tenant's rows: "
        + ", ".join(unscoped)
    )


def test_every_viewset_over_a_tenant_owned_model_is_tenant_scoped() -> None:
    """The contract: routes touching tenant data inherit the base class that filters."""
    tenant_owned = set(_tenant_owned_models())
    offenders = []

    for name, cls in _registered_viewsets().items():
        model = getattr(cls.queryset, "model", None)
        if model not in tenant_owned:
            continue
        if name in SCOPED_BY_MEMBERSHIP:
            continue
        if not issubclass(cls, TenantScopedViewSet):
            offenders.append(f"{name} (model {model.__name__})")

    assert offenders == [], (
        "these viewsets serve tenant-owned models without inheriting TenantScopedViewSet, "
        "so nothing narrows their queryset to the requesting tenant: "
        + ", ".join(offenders)
    )


def test_for_tenant_with_no_tenant_returns_nothing_rather_than_everything() -> None:
    """A bug that loses the tenant must produce an empty list, never a cross-tenant read."""
    for model in _tenant_owned_models():
        assert not model.objects.for_tenant(None).exists()


@pytest.mark.django_db
def test_a_tenant_cannot_read_another_tenants_rows(
    rival_api: APIClient, review: Review, rule_set: RuleSet, ifc_media: Media
) -> None:
    """The behavioural half. The structural tests above say the filter is applied; this
    says it works, over the real HTTP stack, with a real second tenant."""
    for path in ("/api/v1/reviews/", "/api/v1/rule-sets/", "/api/v1/media/"):
        response = rival_api.get(path)
        assert response.status_code == 200, path
        assert response.data["count"] == 0, f"{path} leaked another tenant's rows"

    for path in (
        f"/api/v1/reviews/{review.uuid}/",
        f"/api/v1/rule-sets/{rule_set.uuid}/",
        f"/api/v1/media/{ifc_media.uuid}/",
    ):
        assert rival_api.get(path).status_code == 404, f"{path} was readable across tenants"


@pytest.mark.django_db
def test_naming_a_tenant_you_do_not_belong_to_is_refused(
    other_owner: Any, tenant: Tenant
) -> None:
    """And refused identically to naming one that does not exist.

    Distinguishing the two would turn the tenant header into a way to enumerate the
    customer list.
    """
    client = APIClient()
    client.force_authenticate(user=other_owner)

    not_a_member = client.get("/api/v1/reviews/", HTTP_X_TENANT=tenant.slug)
    does_not_exist = client.get("/api/v1/reviews/", HTTP_X_TENANT="no-such-tenant")

    assert not_a_member.status_code == 403
    assert does_not_exist.status_code == 403
    assert not_a_member.json()["code"] == does_not_exist.json()["code"]


@pytest.mark.django_db
def test_a_request_without_a_tenant_is_refused_rather_than_answered_emptily(
    owner: Any,
) -> None:
    """An empty list would read as 'you have no reviews'. The truth is 'you did not say
    whose reviews', and those are different answers."""
    client = APIClient()
    client.force_authenticate(user=owner)
    assert client.get("/api/v1/reviews/").status_code == 403


@pytest.mark.django_db
def test_tenant_viewset_lists_only_own_tenants(
    rival_api: APIClient, tenant: Tenant
) -> None:
    """The exemption above, covered behaviourally."""
    response = rival_api.get("/api/v1/tenants/")
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert tenant.slug not in slugs
