"""The user.

A custom user model from the first migration, because Django's `AUTH_USER_MODEL` cannot be
changed afterwards without rebuilding every table that points at it. This is the one piece
of scaffolding that is cheaper now than at any later moment.

Identity is the email address. There is no username: a second identifier that nobody uses
is a second thing to keep unique, to validate, and to get wrong.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.repositories.custom_managers import UserManager
from cadgpt.apps.base.models import UuidBaseModel


class User(AbstractBaseUser, PermissionsMixin, UuidBaseModel):
    email = models.EmailField(_("email address"), unique=True, db_index=True)
    full_name = models.CharField(_("full name"), max_length=255, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff"), default=False)

    #: The language this person is written to in, independent of any tenant's default.
    language = models.CharField(_("language"), max_length=8, default="en")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    objects: ClassVar[UserManager] = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.full_name or self.email

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email
