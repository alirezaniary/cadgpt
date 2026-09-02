from __future__ import annotations

from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class SimplePagination(PageNumberPagination):
    """Page-number pagination with a caller-controlled `size`, capped.

    The cap is the point: without it one request can ask for every review a tenant has
    ever run and turn a list endpoint into a denial of service against ourselves.
    """

    page_size = 20
    page_size_query_param = "size"
    max_page_size = 100

    def get_paginated_response(self, data: Any) -> Response:
        # DRF only calls this after `paginate_queryset` has set both, so the optional
        # types on the base class are wider than this call path can produce.
        assert self.page is not None and self.request is not None
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "pages": self.page.paginator.num_pages,
                "size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: Any) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["count", "page", "pages", "size", "results"],
            "properties": {
                "count": {"type": "integer"},
                "page": {"type": "integer"},
                "pages": {"type": "integer"},
                "size": {"type": "integer"},
                "next": {"type": "string", "format": "uri", "nullable": True},
                "previous": {"type": "string", "format": "uri", "nullable": True},
                "results": schema,
            },
        }
