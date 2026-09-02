"""Rule set lifecycle. Validation happens here, at the door, never at check time."""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cadgpt_engine import InvalidIdsError, inspect_ruleset
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from cadgpt.apps.account.models import User
from cadgpt.apps.base.exceptions import ConflictError, ValidationError
from cadgpt.apps.base.files import local_path as _local_path
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

    @contextlib.contextmanager
    def local_path(self, rule_pack: RulePack) -> Iterator[Path]:
        """Yield a filesystem path for `rule_pack`'s IDS file, the same contract
        `media.services.MediaService.local_path` offers for an uploaded file -- both
        delegate to `cadgpt.apps.base.files.local_path`, the one place that fallback
        lives.
        """
        with _local_path(rule_pack.source_file, rule_pack.name) as path:
            yield path

    def checksum_of(self, rule_pack: RulePack) -> str:
        """SHA-256 of `rule_pack`'s IDS bytes, read fresh from storage right now.

        The one hashing primitive both `snapshot` (captured once, at dispatch) and
        `CheckRunExecutor._evaluate_selection` (recomputed, at execution -- T-0031's
        review, F1) share, so a citation's hash and the value it is checked against can
        never disagree because of two hand-rolled loops drifting apart.
        """
        digest = hashlib.sha256()
        rule_pack.source_file.open("rb")
        try:
            for chunk in rule_pack.source_file.chunks():
                digest.update(chunk)
        finally:
            rule_pack.source_file.close()
        return digest.hexdigest()

    def snapshot(self, rule_pack: RulePack) -> dict[str, Any]:
        """The self-contained citation a check run stores for reproducibility.

        Captured at dispatch time as plain data, never a foreign key: `docs/tasks/
        T-0031-rule-selection-on-the-run.md` is explicit that a later catalogue edit --
        a version bumped and seeded as a new row, another pack added -- must never be
        able to redefine what an already-dispatched run is understood to have checked.
        The content hash is computed from the bytes themselves rather than trusted from
        `rule_pack.version`, so the citation survives even a bug that reseeded a pack's
        file under an unchanged version string -- and, since T-0031's review (F1),
        `CheckRunExecutor` recomputes and compares this same hash at execution time
        rather than only ever recording it, so a run whose cited bytes changed underneath
        it refuses instead of silently evaluating whatever is there now.
        """
        return {
            "uuid": str(rule_pack.uuid),
            "name": rule_pack.name,
            "jurisdiction": rule_pack.jurisdiction,
            "region": rule_pack.region,
            "version": rule_pack.version,
            "specification_count": rule_pack.specification_count,
            "checksum_sha256": self.checksum_of(rule_pack),
        }
