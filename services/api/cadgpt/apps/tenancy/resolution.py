"""Resolve which tenant a request is acting in, after the caller has been authenticated.

This deliberately does not run as middleware. Authentication is a bearer token checked by
DRF, and DRF authenticates inside the view -- after every middleware has already run. A
middleware reading `request.user` would see `AnonymousUser` on every API request and
resolve no tenant at all, which is a failure that looks like a permissions bug and is
actually an ordering bug.

So resolution happens on first demand, from a permission class or a viewset, both of which
run after authentication. The result is cached on the request: several permissions and a
queryset all ask, and one membership lookup answers them.
"""

from __future__ import annotations

from typing import Any, cast

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import PermissionDenied

from cadgpt.apps.base.context import tenant_uuid_var
from cadgpt.apps.tenancy.models import Membership

_CACHE_ATTR = "_cadgpt_membership"


class TenantNotAvailable(PermissionDenied):
    """The request named a tenant the caller may not act in.

    Deliberately indistinguishable from naming a tenant that does not exist. Separating
    the two would turn the tenant header into a way to enumerate the customer list.
    """

    default_detail = _("This workspace is not available to you.")
    default_code = "tenant_not_available"


def resolve_membership(request: Any) -> Membership | None:
    """The membership authorizing this request, or None if no tenant was named.

    Returning None rather than raising when the header is absent keeps endpoints that
    precede tenant selection -- signing in, listing your workspaces -- usable. Refusing an
    unauthorized *named* tenant is a different matter and does raise.
    """
    underlying = getattr(request, "_request", request)
    if hasattr(underlying, _CACHE_ATTR):
        return cast("Membership | None", getattr(underlying, _CACHE_ATTR))

    membership = _lookup(request, underlying)

    setattr(underlying, _CACHE_ATTR, membership)
    underlying.tenant = membership.tenant if membership else None
    underlying.membership = membership
    tenant_uuid_var.set(membership.tenant.uuid if membership else None)
    return membership


def _lookup(request: Any, underlying: Any) -> Membership | None:
    slug = underlying.META.get(settings.TENANT_HEADER, "").strip()
    if not slug:
        return None

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise TenantNotAvailable

    membership = cast(
        "Membership | None",
        Membership.objects.active()
        .of_user(user.pk)
        .with_tenant()
        .filter(tenant__slug=slug, tenant__is_active=True)
        .first(),
    )
    if membership is None:
        raise TenantNotAvailable
    return membership


def current_tenant(request: Any) -> Any:
    """The tenant for this request, or None. Never raises for an absent header."""
    membership = resolve_membership(request)
    return membership.tenant if membership else None
