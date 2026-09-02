"""Base viewsets. Every viewset in the project inherits one of these.

Two rules they exist to make structural rather than remembered.

**A serializer is chosen per action.** One serializer serving create, list and a custom
action ends up with a field that is required in one and meaningless in another, and
validation that has to ask which caller it is serving. `serializer_classes` maps action to
serializer and `get_serializer_class` is the only lookup; there is no other place to
special-case.

**A queryset is chosen per action too**, so a list view can prefetch what a detail view
does not need. `select_related`/`prefetch_related` belong in the queryset for the action,
which is the one place an N+1 is visible.
"""

from __future__ import annotations

from typing import Any, ClassVar

from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer


class BaseViewSet(viewsets.GenericViewSet[Any]):
    """Per-action serializer and queryset selection, and lookup by UUID.

    `lookup_field` is the UUID rather than the primary key everywhere: the integer key is
    an implementation detail of the database and must not appear in a URL.
    """

    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    lookup_value_regex = "[0-9a-f-]{36}"

    serializer_classes: ClassVar[dict[str, type[BaseSerializer[Any]]]] = {}
    queryset_selectors: ClassVar[dict[str, tuple[str, ...]]] = {}

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        try:
            return self.serializer_classes[self.action]
        except KeyError:
            pass
        if "default" in self.serializer_classes:
            return self.serializer_classes["default"]
        raise NotImplementedError(
            f"{type(self).__name__} declares no serializer for action "
            f"{self.action!r}. Add it to `serializer_classes`, or a 'default' entry."
        )

    def respond(
        self,
        serializer: BaseSerializer[Any],
        *,
        status: int = http_status.HTTP_200_OK,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """The only way a view produces a body.

        Constructing `Response` inline is how a payload shape drifts away from the
        serializer that is supposed to define it, and how an endpoint ends up
        undocumented in the OpenAPI schema.
        """
        return Response(serializer.data, status=status, headers=headers)
