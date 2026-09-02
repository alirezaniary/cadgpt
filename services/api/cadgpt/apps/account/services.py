"""Account business logic."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.base.services import BaseService


class AccountService(BaseService):
    """Registration and credentials. Not tenant-aware: a person precedes their tenants."""

    def register(
        self, *, email: str, password: str, full_name: str = "", language: str = "en"
    ) -> User:
        self._validate_password(password, email=email, full_name=full_name)
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    email=email,
                    password=password,
                    full_name=full_name.strip(),
                    language=language,
                )
        except IntegrityError as exc:
            # Deliberately the same message a caller would get for any conflict: whether
            # an address is already registered is not something an unauthenticated
            # caller gets to enumerate.
            raise ConflictError(_("This account cannot be created.")) from exc
        except DjangoValidationError as exc:
            raise ValidationError(
                _("The submitted data is not valid."),
                details=exc.message_dict if hasattr(exc, "message_dict") else {},
            ) from exc

        self.log.info("user_registered", user_id=str(user.uuid))
        return user

    def change_password(
        self, *, user: User, current_password: str, new_password: str
    ) -> None:
        if not user.check_password(current_password):
            raise ValidationError(_("The current password is not correct."))
        self._validate_password(new_password, email=user.email, full_name=user.full_name)
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        self.log.info("password_changed", user_id=str(user.uuid))

    def _validate_password(self, password: str, *, email: str, full_name: str) -> None:
        """Django's own validators, run against an unsaved user so similarity works."""
        probe = get_user_model()(email=email, full_name=full_name)
        try:
            validate_password(password, user=probe)
        except DjangoValidationError as exc:
            raise ValidationError(
                _("The password is not acceptable."),
                details={"password": list(exc.messages)},
            ) from exc
