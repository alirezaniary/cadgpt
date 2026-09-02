"""Request context: an id on every request, and that id on every log line it produces."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from cadgpt.apps.base.context import request_id_var, user_uuid_var

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    """Bind a request id and the authenticated user to the ambient logging context.

    An id supplied by the caller is honoured so a trace survives a proxy hop, and echoed
    back on the response so a user reporting a problem can quote the identifier that finds
    their request in the logs.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.META.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        id_token = request_id_var.set(request_id)

        user = getattr(request, "user", None)
        user_uuid = (
            getattr(user, "uuid", None)
            if getattr(user, "is_authenticated", False)
            else None
        )
        user_token = user_uuid_var.set(user_uuid)

        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(id_token)
            user_uuid_var.reset(user_token)

        response[RESPONSE_HEADER] = request_id
        return response
