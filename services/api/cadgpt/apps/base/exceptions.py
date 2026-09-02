"""Domain failures, raised by services and translated at the edge.

A service raises these; it never raises a DRF exception, because the same service is
called from a Celery task and a management command where an HTTP status means nothing.
`drf.exception_handler` is the single place that turns one of these into a response.

Every message is localized. `code` is not: it is the stable identifier a client switches
on, and it must survive translation.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _


class DomainError(Exception):
    """Base class for every failure the domain raises on purpose."""

    code = "domain_error"
    default_message = _("The request could not be completed.")

    def __init__(
        self,
        message: Any | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message if message is not None else self.default_message
        self.code = code or self.code
        self.details = details or {}
        super().__init__(str(self.message))


class ValidationError(DomainError):
    code = "validation_error"
    default_message = _("The submitted data is not valid.")


class NotFoundError(DomainError):
    code = "not_found"
    default_message = _("The requested resource does not exist.")


class PermissionDeniedError(DomainError):
    code = "permission_denied"
    default_message = _("You do not have permission to perform this action.")


class ConflictError(DomainError):
    """The request is well formed but contradicts the current state of the resource."""

    code = "conflict"
    default_message = _("The resource is not in a state that allows this action.")
