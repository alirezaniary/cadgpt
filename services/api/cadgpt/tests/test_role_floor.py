"""Every action that queues work must require at least `IsTenantMemberOrAbove`.

T-0060: `CheckRunViewSet.generate_report` (dispatches `generate_report_file` onto the
shared `checks` queue) disagreed with `ReviewViewSet.check` (dispatches a check onto the
same queue) about who may call it -- `generate_report` had no floor above
`IsTenantMember`, so a VIEWER, documented as "may read the tenant's work but change
nothing" (`tenancy/permissions.py`), could queue work anyway.

`test_every_work_queuing_action_requires_at_least_member` below is the structural half of
the fix. A test asserting that today's two actions each carry `IsTenantMemberOrAbove`
would not have caught this defect -- both already claimed to, in a permission tuple
nobody was cross-checking -- and would not catch the next one either. Instead, the same
way `test_tenant_isolation.py` walks every registered route and fails the build when one
escapes `TenantScopedViewSet`, this walks every registered route and every DRF `@action`
that answers a write HTTP verb -- the definition of "queues work beyond simple CRUD" this
task settled on -- and derives, from the viewset's own `get_permissions()`, whether that
action's floor is at least `MEMBER`. It fails the moment a *new* action is added without
one, not just when today's two regress.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient

from cadgpt.apps.review.choices import CheckRunStatus
from cadgpt.apps.review.models import Review
from cadgpt.apps.tenancy.choices import ROLE_RANK, MembershipRole
from cadgpt.apps.tenancy.permissions import _MinimumRole

#: HTTP verbs that write. An extra `@action` answering only `get` is a read -- e.g.
#: `CheckRunViewSet.report_file` -- and out of this test's scope.
_WRITE_METHODS = {"post", "put", "patch", "delete"}


def _routed_views() -> list[Any]:
    """Every `as_view()` callback reachable through the project's URL configuration.

    Mirrors `test_tenant_isolation._registered_viewsets`'s resolver walk, but keeps the
    callback itself rather than collapsing it to a bare class. `CheckRunViewSet` alone is
    reached through three separate `as_view()` calls (`run_list`, `run_detail`,
    `run_report_file` in `review/api/v1/urls.py`), each with its own `.actions` method
    map and its own `.initkwargs` -- and a hand-wired call like `run_report_file` carries
    no `@action` kwargs in its `.initkwargs` at all, unlike a router-registered one. A
    class-level view loses that distinction entirely, which is exactly the gap that let
    a hand-wired route's dead `@action(permission_classes=...)` read as live.
    """
    callbacks: list[Any] = []

    def walk(resolver: Any) -> None:
        for pattern in resolver.url_patterns:
            if hasattr(pattern, "url_patterns"):
                walk(pattern)
                continue
            callback = pattern.callback
            cls = getattr(callback, "cls", None)
            if cls is not None and hasattr(cls, "queryset"):
                callbacks.append(callback)

    walk(get_resolver())
    return callbacks


def _write_extra_actions(cls: type[Any]) -> set[str]:
    """The names of this viewset's `@action`-decorated methods answering a write verb.

    `get_extra_actions()` is DRF's own introspection (`ViewSetMixin.get_extra_actions`),
    independent of how a particular deployment wired the URL -- it is true of the class,
    not of one route to it. `list`/`retrieve`/`create`/`update`/`partial_update`/`destroy`
    are never in this list; they come from mixins, not `@action`, which is exactly the
    "beyond simple CRUD" boundary this task drew.
    """
    return {
        action.__name__
        for action in cls.get_extra_actions()
        if _WRITE_METHODS & set(action.mapping)
    }


def _permissions_for_route(callback: Any, action_name: str) -> list[Any]:
    """The permission instances DRF would actually build for one call to this route.

    `callback.initkwargs` is whatever was actually passed to *this route's*
    `as_view(...)` call -- for a router-registered action that includes the
    `@action(..., permission_classes=...)` kwargs the router injects
    (`SimpleRouter._get_dynamic_route` merges `action.kwargs` into the initkwargs it
    passes to `as_view`), the way `MembershipViewSet.invite`/`.revoke` rely on. For a
    hand-wired `as_view({...})` call -- `CheckRunViewSet`'s nested routes -- it is only
    whatever was explicitly passed there, which for `run_report_file` is nothing: a
    `permission_classes` kwarg on the `@action` decorator itself would be silently inert
    on that route, and crediting it anyway is exactly the false pass this test used to
    produce. Constructing `callback.cls(**callback.initkwargs)` reproduces
    `ViewSetMixin.as_view`'s own `self = cls(**initkwargs)` line for word; setting
    `.action` reproduces the other half -- `initialize_request` setting it from
    `self.action_map[request.method]` -- so a `get_permissions()` override that branches
    on `self.action` instead, the way `ReviewViewSet` and `CheckRunViewSet` both do, is
    exercised correctly regardless of which style guards the action.
    """
    view = callback.cls(**callback.initkwargs)
    view.action = action_name
    return list(view.get_permissions())


def _minimum_role_rank(permissions: list[Any]) -> int | None:
    """The highest role floor any permission in this list actually asserts.

    `None` means no permission here is a `_MinimumRole` at all -- `IsTenantMember` only
    asserts a membership exists (rank is not part of its contract), which is exactly the
    gap this task closed. DRF's `has_permission` is an AND across the list, so it is
    correct to take the *strongest* floor present: whichever permission demands the most
    is the one that actually gates the request.
    """
    ranks = [ROLE_RANK[p.required_role] for p in permissions if isinstance(p, _MinimumRole)]
    return max(ranks) if ranks else None


def test_every_work_queuing_action_requires_at_least_member() -> None:
    """The structural half of T-0060. See module docstring.

    Walks actual routes, not classes: an extra action is only checked through the
    specific `as_view()` callback that answers it, using *that* callback's own
    `.initkwargs` to resolve permissions -- see `_permissions_for_route`. A class
    reached through several routes (`CheckRunViewSet`) is checked once per route, so a
    hand-wired route that fails to carry a router's `@action` kwargs is caught even when
    the same class also has a properly-guarded, router-registered action elsewhere.
    """
    required = ROLE_RANK[MembershipRole.MEMBER]
    offenders = []
    checked: set[tuple[int, str]] = set()

    for callback in _routed_views():
        cls = callback.cls
        write_extra_actions = _write_extra_actions(cls)
        for method, action_name in callback.actions.items():
            if method not in _WRITE_METHODS or action_name not in write_extra_actions:
                continue
            key = (id(callback), action_name)
            if key in checked:
                continue
            checked.add(key)
            permissions = _permissions_for_route(callback, action_name)
            floor = _minimum_role_rank(permissions)
            if floor is None or floor < required:
                seen = ", ".join(type(p).__name__ for p in permissions) or "(none)"
                offenders.append(
                    f"{cls.__name__}.{action_name} (permissions resolved to: {seen})"
                )

    assert offenders == [], (
        "these actions dispatch work through a write HTTP verb but do not require at "
        "least IsTenantMemberOrAbove, so a VIEWER could queue work through them: "
        + "; ".join(offenders)
    )


@pytest.mark.django_db
def test_a_viewer_cannot_queue_a_check(viewer_api: APIClient, review: Review) -> None:
    """The behavioural half for `ReviewViewSet.check`, over real HTTP."""
    response = viewer_api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert response.status_code == 403, response.data


@pytest.mark.django_db
def test_role_floor_on_generate_report(
    api: APIClient,
    viewer_api: APIClient,
    member_api: APIClient,
    review: Review,
    commit: Any,
) -> None:
    """The behavioural half for `CheckRunViewSet.generate_report`, over real HTTP.

    Needs a succeeded run to reach the permission check meaningfully rather than
    short-circuiting on the earlier 409 ("only a succeeded run may generate a report"),
    so this drives one through the real executor first, as the tenant's owner, exactly
    the way `test_check_run.py` does end to end.

    Refusal and acceptance are asserted on the *same* run: a VIEWER in this tenant is
    refused, and a MEMBER in the same tenant -- above the floor `IsTenantMemberOrAbove`
    requires, but nothing more privileged than that -- is accepted.
    """
    with commit():
        queued = api.post(f"/api/v1/reviews/{review.uuid}/check/")
    assert queued.status_code == 202, queued.data
    run_uuid = queued.data["uuid"]

    refused = viewer_api.post(f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/report-file/")
    assert refused.status_code == 403, refused.data

    with commit():
        accepted = member_api.post(
            f"/api/v1/reviews/{review.uuid}/runs/{run_uuid}/report-file/"
        )
    assert accepted.status_code == 202, accepted.data
    assert accepted.data["status"] == CheckRunStatus.SUCCEEDED
