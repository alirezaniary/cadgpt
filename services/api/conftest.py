"""Shared fixtures. Every one builds a real row through the real service.

There are no mocks here and none in the API tests. A fixture that seeded the database
directly would let a service's validation rot unnoticed -- this repository has a
documented history of suites passing while nothing worked.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from cadgpt.apps.account.models import User
from cadgpt.apps.account.services import AccountService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.review.models import Review
from cadgpt.apps.review.services import ReviewService
from cadgpt.apps.rulepack.models import RulePack, RuleSet
from cadgpt.apps.rulepack.services import RulePackService, RuleSetService
from cadgpt.apps.tenancy.models import Tenant
from cadgpt.apps.tenancy.services import TenantProvisioningService
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

# The same real files the engine is tested against: three doors, one of which is too
# narrow and one of which records no width at all.
ENGINE_FIXTURES = (
    Path(__file__).resolve().parents[2] / "packages" / "engine" / "tests" / "fixtures"
)
IFC_FIXTURE = ENGINE_FIXTURES / "three_doors.ifc"
IDS_FIXTURE = ENGINE_FIXTURES / "door_width.ids"

PASSWORD = "correct-horse-battery"


@pytest.fixture
def owner(db: Any) -> User:
    return AccountService().register(
        email="owner@example.test", password=PASSWORD, full_name="Owner"
    )


@pytest.fixture
def other_owner(db: Any) -> User:
    return AccountService().register(
        email="rival@example.test", password=PASSWORD, full_name="Rival"
    )


@pytest.fixture
def tenant(owner: User) -> Tenant:
    return TenantProvisioningService().create(name="Atelier", slug="atelier", owner=owner)


@pytest.fixture
def other_tenant(other_owner: User) -> Tenant:
    return TenantProvisioningService().create(name="Rival", slug="rival", owner=other_owner)


def _upload(path: Path, content_type: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(path.name, path.read_bytes(), content_type=content_type)


@pytest.fixture
def ifc_media(tenant: Tenant, owner: User) -> Media:
    return MediaService(tenant=tenant).store(
        upload=_upload(IFC_FIXTURE, "application/octet-stream"),
        kind=MediaKind.IFC_MODEL,
        uploaded_by=owner,
    )


@pytest.fixture
def ids_media(tenant: Tenant, owner: User) -> Media:
    return MediaService(tenant=tenant).store(
        upload=_upload(IDS_FIXTURE, "application/xml"),
        kind=MediaKind.IDS_RULESET,
        uploaded_by=owner,
    )


@pytest.fixture
def rule_set(tenant: Tenant, owner: User, ids_media: Media) -> RuleSet:
    return RuleSetService(tenant=tenant).create(
        source_file=ids_media, name="Accessible doors", created_by=owner
    )


@pytest.fixture
def rule_pack(db: Any) -> RulePack:
    """A catalogue pack. Belongs to no tenant -- `db` is the only fixture it needs."""
    pack, _ = RulePackService().seed(
        ids_path=IDS_FIXTURE,
        jurisdiction="sample",
        region="",
        version="0.1",
        source_citation="test fixture, seeded for the test suite; not a real regulation.",
    )
    return pack


@pytest.fixture
def review(tenant: Tenant, owner: User, ifc_media: Media, rule_set: RuleSet) -> Review:
    return ReviewService(tenant=tenant).create(
        name="Ground floor", model_file=ifc_media, rule_set=rule_set, created_by=owner
    )


@pytest.fixture
def api(owner: User, tenant: Tenant) -> APIClient:
    """A client authenticated as `owner`, acting in `tenant`.

    The tenant header is set once here because every tenant-scoped request needs it, and
    a test that forgets it would get an empty list rather than a failure -- which is
    exactly the confusion `IsTenantMember` exists to prevent.
    """
    client = APIClient()
    client.force_authenticate(user=owner)
    client.defaults["HTTP_X_TENANT"] = tenant.slug
    return client


@pytest.fixture
def rival_api(other_owner: User, other_tenant: Tenant) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=other_owner)
    client.defaults["HTTP_X_TENANT"] = other_tenant.slug
    return client


@pytest.fixture
def commit(django_capture_on_commit_callbacks: Any) -> Callable[[], Any]:
    """Run the `transaction.on_commit` callbacks a block registers.

    A check is dispatched to the queue on commit, never inside the transaction that
    created its run -- otherwise a worker can pick the message up before the row it names
    is visible to any other connection. Tests run inside a transaction that is rolled
    back, so nothing ever commits and the callbacks would never fire. Wrapping the request
    in this makes the test exercise the same ordering production uses instead of quietly
    testing a path where the task never ran.
    """

    @contextlib.contextmanager
    def _commit() -> Iterator[None]:
        with django_capture_on_commit_callbacks(execute=True):
            yield

    return _commit
