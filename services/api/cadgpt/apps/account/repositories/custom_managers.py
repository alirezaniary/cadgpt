"""Managers are thin. They create; they do not decide.

A manager method exists so a serializer or an admin form never calls `Model(...)` and
`save()` directly. What may be created, and under what conditions, is the service's
question -- the manager only knows how to write the row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import BaseUserManager
from django.db.models.manager import Manager

from cadgpt.apps.account.repositories.querysets import UserQuerySet

if TYPE_CHECKING:
    from cadgpt.apps.account.models import User

_Queryset_Base = Manager.from_queryset(UserQuerySet)

if TYPE_CHECKING:
    _Base = _Queryset_Base["User"]
else:
    _Base = _Queryset_Base


class UserManager(BaseUserManager["User"], _Base):
    """Django requires this shape for `createsuperuser` and the auth backend."""

    use_in_migrations = False

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        if not email:
            raise ValueError("A user must have an email address.")
        user = self.model(email=self.normalize_email(email).strip(), **extra)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if not (extra["is_staff"] and extra["is_superuser"]):
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        return self.create_user(email, password, **extra)
