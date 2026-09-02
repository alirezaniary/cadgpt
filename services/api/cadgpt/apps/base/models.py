"""Abstract bases. Models here hold no business logic -- that lives in services.

A model may enforce an invariant that must be true of a row regardless of who wrote it.
It may not orchestrate, call another aggregate, or produce a side effect; `save()` and
`clean()` stay free of both, which is what keeps a service the only place a reader has to
look to find out what happens when something is created.
"""

from __future__ import annotations

import uuid as uuid_lib
from typing import Any, ClassVar

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.querysets import AllObjectsManager, DeletedManager, SoftDeleteManager


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class UuidBaseModel(TimeStampedModel):
    """The default base: an integer primary key for the database, a UUID for the world.

    Joins and indexes stay narrow and locally ordered on the integer key, while nothing
    outside the process ever sees it. Exposing a sequential id in a URL would let one
    tenant count another's work and guess at neighbouring rows; the UUID is what appears
    in an API response, a report, and a log line.
    """

    uuid = models.UUIDField(
        _("uuid"), default=uuid_lib.uuid4, unique=True, editable=False, db_index=True
    )

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.uuid})"


class SoftDeleteModelMixin(models.Model):
    """Deletion that a person can undo, for rows that represent someone's work.

    Three managers, because the default has to be the safe one: `objects` hides deleted
    rows, `objects_deleted` shows only those, `objects_with_deleted` sees everything. Code
    that forgets which it wanted gets the safe answer.
    """

    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True, default=None)

    objects: ClassVar[SoftDeleteManager] = SoftDeleteManager()
    objects_deleted: ClassVar[DeletedManager] = DeletedManager()
    objects_with_deleted: ClassVar[AllObjectsManager] = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(
        self, using: str | None = None, keep_parents: bool = False, hard: bool = False
    ) -> Any:
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.deleted_at = timezone.now()
        self.save(update_fields=self._soft_delete_fields())
        return (0, {})

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=self._soft_delete_fields())

    def _soft_delete_fields(self) -> list[str]:
        """`deleted_at`, plus `updated_at` when the host model has one.

        The mixin cannot assume the timestamp fields, because it is composed onto models
        that may not carry them -- and naming a field that does not exist in
        `update_fields` is an error at save time, not at import time.
        """
        names = {field.name for field in self._meta.fields}
        return ["deleted_at", *(["updated_at"] if "updated_at" in names else [])]
