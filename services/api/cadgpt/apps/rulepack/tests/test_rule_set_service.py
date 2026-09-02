"""A rule set is read before it is accepted, never at check time."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.rulepack.models import RuleSet
from cadgpt.apps.rulepack.services import RuleSetService
from cadgpt.apps.tenancy.models import Tenant

pytestmark = pytest.mark.django_db


def test_registering_a_rule_set_records_what_it_will_check(
    tenant: Tenant, owner: Any, ids_media: Media
) -> None:
    rule_set = RuleSetService(tenant=tenant).create(
        source_file=ids_media, name="Doors", created_by=owner
    )
    assert rule_set.title == "Accessible door width"
    assert rule_set.specification_count == 1


def test_a_malformed_ids_is_refused_at_upload_not_at_check_time(
    tenant: Tenant, owner: Any
) -> None:
    """A broken rule set found minutes later, mid-check, is an error nobody can act on."""
    media = MediaService(tenant=tenant).store(
        upload=SimpleUploadedFile("broken.ids", b"<ids>not an ids</ids>"),
        kind=MediaKind.IDS_RULESET,
        uploaded_by=owner,
    )
    with pytest.raises(ValidationError):
        RuleSetService(tenant=tenant).create(source_file=media, name="Broken")


def test_a_model_file_cannot_be_registered_as_a_rule_set(
    tenant: Tenant, owner: Any, ifc_media: Media
) -> None:
    with pytest.raises(ValidationError):
        RuleSetService(tenant=tenant).create(source_file=ifc_media, name="Wrong kind")


def test_two_rule_sets_in_one_tenant_may_not_share_a_name(
    tenant: Tenant, owner: Any, ids_media: Media
) -> None:
    RuleSetService(tenant=tenant).create(source_file=ids_media, name="Doors")
    with pytest.raises(ConflictError):
        RuleSetService(tenant=tenant).create(source_file=ids_media, name="Doors")


def test_an_archived_rule_set_stays_readable_to_the_run_that_used_it(
    tenant: Tenant, rule_set: RuleSet
) -> None:
    """Deleting it would make an existing report unexplainable."""
    RuleSetService(tenant=tenant).archive(rule_set=rule_set)

    assert not RuleSet.objects.for_tenant(tenant).filter(pk=rule_set.pk).exists()
    assert RuleSet.objects_with_deleted.filter(pk=rule_set.pk).exists()
