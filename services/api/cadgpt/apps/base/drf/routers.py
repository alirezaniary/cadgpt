"""Routing with an explicit scope.

An API scope is an audience: the tenant-facing API, and later an administrative or a
public one. They have different authentication, different serializers and different
stability guarantees, and they will eventually hold resources of the same name.

`ScopedRouter` prefixes every generated URL name with its scope, so `reverse()` can never
resolve to the wrong audience's route, and a basename collision inside one scope is an
error at import time rather than a route that silently shadows another.
"""

from __future__ import annotations

from typing import Any

from rest_framework.routers import DefaultRouter


class ScopedRouter(DefaultRouter):
    """A `DefaultRouter` whose URL names are namespaced by API scope."""

    def __init__(self, scope: str, **kwargs: Any) -> None:
        if not scope:
            raise ValueError("A ScopedRouter must be given a non-empty scope.")
        self.scope = scope
        self._basenames: set[str] = set()
        kwargs.setdefault("trailing_slash", True)
        super().__init__(**kwargs)
        self.include_root_view = False

    def register(
        self, prefix: str, viewset: Any, basename: str | None = None, **kwargs: Any
    ) -> None:
        if basename is None:
            basename = self.get_default_basename(viewset)
        if basename in self._basenames:
            raise ValueError(
                f"basename {basename!r} is already registered in the {self.scope!r} "
                "scope; two routes would answer to the same reverse() name."
            )
        self._basenames.add(basename)
        super().register(prefix, viewset, basename=f"{self.scope}-{basename}", **kwargs)
