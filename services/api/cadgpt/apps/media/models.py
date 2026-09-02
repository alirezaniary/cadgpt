from __future__ import annotations

import uuid as uuid_lib
from pathlib import PurePosixPath
from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.base.models import UuidBaseModel
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.repositories.custom_managers import MediaManager
from cadgpt.apps.tenancy.models import TenantOwnedModel


def upload_to(instance: Media, filename: str) -> str:
    """Partition storage by tenant, then by kind.

    The path carries no user-supplied component beyond the extension: an original filename
    can contain path separators, unicode that normalises to `..`, or 4KB of text, and none
    of that belongs in a storage key. The original is kept in a column instead, where it
    is data rather than a path.
    """
    suffix = PurePosixPath(filename).suffix.lower()[:16]
    return f"tenants/{instance.tenant.uuid}/{instance.kind}/{uuid_lib.uuid4()}{suffix}"


class Media(TenantOwnedModel, UuidBaseModel):
    """One stored file, owned by exactly one tenant."""

    tenant_related_name = "media"

    file = models.FileField(_("file"), upload_to=upload_to, max_length=512)
    kind = models.CharField(_("kind"), max_length=32, choices=MediaKind.choices)
    original_name = models.CharField(_("original file name"), max_length=255)
    content_type = models.CharField(_("content type"), max_length=128, blank=True)
    size_bytes = models.BigIntegerField(_("size in bytes"))

    #: Identifies the bytes independently of the name. Two uploads of the same model are
    #: recognisable as the same model, and a stored report can name the exact input it
    #: was produced from -- which is what makes an old run reproducible.
    checksum_sha256 = models.CharField(_("SHA-256"), max_length=64, db_index=True)

    uploaded_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_media",
        verbose_name=_("uploaded by"),
    )

    objects: ClassVar[MediaManager] = MediaManager()

    class Meta:
        verbose_name = _("media")
        verbose_name_plural = _("media")
        ordering = ("-created_at",)
        indexes = (
            models.Index(fields=("tenant", "kind", "-created_at")),
            models.Index(fields=("tenant", "checksum_sha256")),
        )

    def __str__(self) -> str:
        return self.original_name
