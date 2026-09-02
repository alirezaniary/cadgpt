"""One place turns a failure into a response.

The shape is RFC 9457 problem details. Two properties matter more than the format: `code`
is a stable machine identifier that survives translation, and `detail` is localized into
the requesting user's language, because the tenants are multinational and an English-only
error is unusable to half of them.

An unexpected exception is logged with its traceback and answered with an opaque 500. It
is never swallowed and never leaked -- a stack trace in a response tells an attacker the
shape of the system.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions as drf_exceptions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from cadgpt.apps.base.context import current_request_id
from cadgpt.apps.base.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

log = structlog.get_logger(__name__)

_DOMAIN_STATUS: dict[type[DomainError], int] = {
    ValidationError: status.HTTP_400_BAD_REQUEST,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
}


def _problem(*, http_status: int, code: str, detail: Any, errors: Any = None) -> Response:
    body: dict[str, Any] = {
        "type": f"about:blank#{code}",
        "status": http_status,
        "code": code,
        "detail": str(detail),
    }
    if errors:
        body["errors"] = errors
    if (request_id := current_request_id()) is not None:
        body["request_id"] = request_id
    return Response(body, status=http_status)


def _status_for(exc: DomainError) -> int:
    for domain_type, http_status in _DOMAIN_STATUS.items():
        if isinstance(exc, domain_type):
            return http_status
    return status.HTTP_400_BAD_REQUEST


def problem_detail_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF's `EXCEPTION_HANDLER`. Returns None only for what should become a 500."""
    if isinstance(exc, DomainError):
        return _problem(
            http_status=_status_for(exc),
            code=exc.code,
            detail=exc.message,
            errors=exc.details or None,
        )

    if isinstance(exc, Http404):
        return _problem(
            http_status=status.HTTP_404_NOT_FOUND,
            code="not_found",
            detail=_("The requested resource does not exist."),
        )

    if isinstance(exc, DjangoPermissionDenied):
        return _problem(
            http_status=status.HTTP_403_FORBIDDEN,
            code="permission_denied",
            detail=_("You do not have permission to perform this action."),
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        # Nothing recognised it. Log it whole, answer with nothing.
        log.exception("unhandled_exception", view=str(context.get("view")))
        return _problem(
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            detail=_("The request could not be completed."),
        )

    if isinstance(exc, drf_exceptions.ValidationError):
        return _problem(
            http_status=response.status_code,
            code="validation_error",
            detail=_("The submitted data is not valid."),
            errors=response.data,
        )

    api_exc = exc if isinstance(exc, drf_exceptions.APIException) else None
    detail = getattr(api_exc, "detail", None) or _("The request could not be completed.")
    code = str(getattr(detail, "code", None) or getattr(api_exc, "default_code", "error"))
    return _problem(http_status=response.status_code, code=code, detail=detail)
