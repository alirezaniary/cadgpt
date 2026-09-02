"""Permissions, which are also where the tenant is resolved.

They run after authentication and before the view body, which is the only point where the
caller is known and no query has been issued yet.
"""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from cadgpt.apps.tenancy.choices import MembershipRole
from cadgpt.apps.tenancy.resolution import resolve_membership


class IsTenantMember(BasePermission):
    """A tenant must have been named and the caller must belong to it.

    Without this, a request that omits the tenant header reaches a view whose queryset
    filters on `None` and returns an empty list -- a 200 that reads like "you have no
    reviews" when the truth is "you did not say whose reviews".
    """

    message = "Select a workspace before making this request."

    def has_permission(self, request: Request, view: Any) -> bool:  # noqa: ARG002
        return resolve_membership(request) is not None


class _MinimumRole(BasePermission):
    required_role: str

    def has_permission(self, request: Request, view: Any) -> bool:  # noqa: ARG002
        membership = resolve_membership(request)
        return membership is not None and membership.has_at_least(self.required_role)


class IsTenantViewer(_MinimumRole):
    """May read the tenant's work but change nothing."""

    message = "Your role in this workspace does not allow this action."
    required_role = MembershipRole.VIEWER


class IsTenantMemberOrAbove(_MinimumRole):
    """May create work: upload models, define rule sets, start checks."""

    message = "Your role in this workspace does not allow this action."
    required_role = MembershipRole.MEMBER


class IsTenantAdmin(_MinimumRole):
    message = "Only a workspace administrator may perform this action."
    required_role = MembershipRole.ADMIN
