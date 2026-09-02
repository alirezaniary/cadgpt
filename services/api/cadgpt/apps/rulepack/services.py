"""Rule set lifecycle. Validation happens here, at the door, never at check time."""

from __future__ import annotations

from pathlib import Path

from cadgpt_engine import InvalidIdsError, inspect_ruleset
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.base.services import BaseService, BaseTenantAwareService
from cadgpt.apps.media.choices import MediaKind
from cadgpt.apps.media.models import Media
from cadgpt.apps.media.services import MediaService
from cadgpt.apps.rulepack.models import RulePack, RuleSet


class RuleSetService(BaseTenantAwareService):
    """Accepts an uploaded IDS only after reading it."""

    def create(
        self,
        *,
        source_file: Media,
        name: str,
        description: str = "",
        created_by: User | None = None,
    ) -> RuleSet:
        """Validate the IDS and record what it contains.

        The file is parsed here rather than when a check runs, so a broken rule set is
        one immediate, actionable error instead of a check that fails minutes later for a
        reason the user cannot connect to what they did.
        """
        if source_file.kind != MediaKind.IDS_RULESET:
            raise ValidationError(_("That file was not uploaded as a rule set."))

        with MediaService(tenant=self.tenant).local_path(source_file) as path:
            try:
                summary = inspect_ruleset(path)
            except InvalidIdsError as exc:
                raise ValidationError(
                    _("This file is not a valid IDS rule set."),
                    details={"source_file": [str(exc)]},
                ) from exc

        try:
            with transaction.atomic():
                rule_set = RuleSet.objects.create_rule_set(
                    tenant=self.tenant,
                    name=name or summary.title or source_file.original_name,
                    description=description or summary.description,
                    source_file=source_file,
                    title=summary.title,
                    author=summary.author,
                    version=summary.version,
                    specification_count=summary.specification_count,
                    created_by=created_by,
                )
        except IntegrityError as exc:
            raise ConflictError(
                _("A rule set with this name already exists in this workspace.")
            ) from exc

        self.log.info(
            "rule_set_created",
            rule_set_id=str(rule_set.uuid),
            specifications=summary.specification_count,
        )
        return rule_set

    def archive(self, *, rule_set: RuleSet) -> None:
        """Soft delete. A completed run's rule set stays readable, or its report lies."""
        rule_set.delete()
        self.log.info("rule_set_archived", rule_set_id=str(rule_set.uuid))


class RulePackService(BaseService):
    """The only way a pack enters the catalogue. Not tenant-aware -- a shipped pack
    belongs to no tenant, and this is called by a management command, never a request.
    """

    def seed(
        self,
        *,
        ids_path: Path,
        jurisdiction: str,
        region: str,
        version: str,
        source_citation: str,
    ) -> tuple[RulePack, bool]:
        """Load `ids_path` into the catalogue, unless a pack already sits at this identity.

        Idempotent by construction, and idempotent honestly rather than by overwriting:
        (jurisdiction, region, version, name) is looked up *before* the file is even
        parsed, so a re-run neither duplicates the row nor silently replaces one an
        earlier run already cited -- it reports what it found and changes nothing.
        Returns the pack and whether this call created it.
        """
        try:
            summary = inspect_ruleset(ids_path)
        except InvalidIdsError as exc:
            raise ValidationError(
                _("This file is not a valid IDS rule set."),
                details={"source_file": [str(exc)]},
            ) from exc

        name = summary.title or ids_path.stem
        existing = RulePack.objects.matching(
            jurisdiction=jurisdiction, region=region, version=version, name=name
        ).first()
        if existing is not None:
            self.log.info(
                "rule_pack_seed_skipped",
                rule_pack_id=str(existing.uuid),
                name=name,
                jurisdiction=jurisdiction,
                region=region,
                version=version,
            )
            return existing, False

        rule_pack = RulePack.objects.create_rule_pack(
            name=name,
            description=summary.description,
            jurisdiction=jurisdiction,
            region=region,
            version=version,
            source_file=ContentFile(ids_path.read_bytes(), name=ids_path.name),
            source_citation=source_citation,
            title=summary.title,
            author=summary.author,
            specification_count=summary.specification_count,
        )
        self.log.info(
            "rule_pack_seeded",
            rule_pack_id=str(rule_pack.uuid),
            name=name,
            jurisdiction=jurisdiction,
            region=region,
            version=version,
            specifications=summary.specification_count,
        )
        return rule_pack, True
