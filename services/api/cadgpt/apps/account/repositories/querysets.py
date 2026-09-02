from __future__ import annotations

from typing import TYPE_CHECKING, Self

from cadgpt.apps.base.querysets import BaseQuerySet

if TYPE_CHECKING:
    # Imported for the quoted type parameter on the queryset below, which ruff
    # does not read as a use. Importing at runtime would be a cycle: the model
    # module imports the manager, which imports this one.
    from cadgpt.apps.account.models import User  # noqa: F401


class UserQuerySet(BaseQuerySet["User"]):
    def active(self) -> Self:
        return self.filter(is_active=True)

    def by_email(self, email: str) -> Self:
        """Email is matched case-insensitively but stored as the user typed it."""
        return self.filter(email__iexact=email.strip())

    def members_of(self, tenant_id: int) -> Self:
        return self.filter(memberships__tenant_id=tenant_id, memberships__is_active=True)
