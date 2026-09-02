"""What may be stored, and what the stored row records about it."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from cadgpt.apps.base.exceptions import ValidationError
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.tenancy.models import Tenant

pytestmark = pytest.mark.django_db


def test_an_upload_records_a_checksum_of_its_actual_bytes(
    tenant: Tenant, owner: Any
) -> None:
    """The checksum is what lets a run name the exact input it read."""
    content = b"ISO-10303-21;\nENDSEC;\n"
    media = MediaService(tenant=tenant).store(
        upload=SimpleUploadedFile("model.ifc", content),
        kind=MediaKind.IFC_MODEL,
        uploaded_by=owner,
    )
    assert media.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert media.size_bytes == len(content)


def test_the_stored_path_carries_no_user_supplied_name(tenant: Tenant, owner: Any) -> None:
    """An original filename can hold separators and traversal; it belongs in a column."""
    media = MediaService(tenant=tenant).store(
        upload=SimpleUploadedFile("../../etc/passwd.ifc", b"ISO-10303-21;"),
        kind=MediaKind.IFC_MODEL,
        uploaded_by=owner,
    )
    stored = media.file.name
    assert stored is not None
    assert ".." not in stored
    assert str(tenant.uuid) in stored
    assert stored.endswith(".ifc")


def test_a_file_of_the_wrong_type_is_refused(tenant: Tenant, owner: Any) -> None:
    with pytest.raises(ValidationError):
        MediaService(tenant=tenant).store(
            upload=SimpleUploadedFile("model.dwg", b"not ifc"),
            kind=MediaKind.IFC_MODEL,
            uploaded_by=owner,
        )


def test_an_empty_file_is_refused(tenant: Tenant, owner: Any) -> None:
    """An empty model would produce a rule set that matched nothing and looked green."""
    with pytest.raises(ValidationError):
        MediaService(tenant=tenant).store(
            upload=SimpleUploadedFile("model.ifc", b""),
            kind=MediaKind.IFC_MODEL,
            uploaded_by=owner,
        )


def test_a_rule_set_larger_than_its_own_limit_is_refused(
    tenant: Tenant, owner: Any
) -> None:
    """The per-kind cap stops a rule-set upload becoming a way past the model limit."""
    from cadgpt.apps.media.constants import MAX_BYTES

    oversize = b"x" * (MAX_BYTES[MediaKind.IDS_RULESET] + 1)
    with pytest.raises(ValidationError):
        MediaService(tenant=tenant).store(
            upload=SimpleUploadedFile("rules.ids", oversize),
            kind=MediaKind.IDS_RULESET,
            uploaded_by=owner,
        )
