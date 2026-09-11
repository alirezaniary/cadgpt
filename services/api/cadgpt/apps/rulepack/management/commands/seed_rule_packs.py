"""Seed the rule pack catalogue from IDS files already in this repository.

Idempotent: `RulePackService.seed` looks a pack's identity up -- (jurisdiction, region,
version, name) -- *before* touching the file, so re-running this command neither
duplicates a row nor overwrites one an earlier run already cited. CLAUDE.md: every
background task is idempotent, and a seeder is held to the same standard.

No rule content is authored here. `docs/tasks/T-0030-the-rule-catalogue.md` is explicit
that the product owner authors real packs -- Iranian building code first, then EU and US
-- in a separate thread, and that this loop must not invent jurisdictions, region codes
or version strings for packs that do not exist. The manifest below seeds the engine's own
IDS test fixtures under an honest "sample" jurisdiction that says exactly what it is: a
development fixture, not a regulation, present only to exercise the storage and selection
path ahead of that authoring work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from cadgpt.apps.rulepack.models import RulePack
from cadgpt.apps.rulepack.services import RulePackService

# services/api/cadgpt/apps/rulepack/management/commands/ -> repo root, matching how
# conftest.py finds the same directory for the API test suite.
ENGINE_FIXTURES = (
    settings.BASE_DIR.parent.parent / "packages" / "engine" / "tests" / "fixtures"
)


@dataclass(frozen=True, slots=True)
class SeedEntry:
    filename: str
    jurisdiction: str
    region: str
    version: str
    source_citation: str


def _fixture_citation(filename: str) -> str:
    return (
        f"cadgpt engine test fixture (packages/engine/tests/fixtures/{filename} in this "
        "repository). Not an authored regulation -- seeded to exercise the rule pack "
        "catalogue's storage and selection path ahead of the product owner's authored "
        "packs (docs/plan.md, Phase 3: Iranian building code first, then EU and US)."
    )


SEED_MANIFEST: tuple[SeedEntry, ...] = tuple(
    SeedEntry(
        filename=filename,
        jurisdiction="sample",
        region="",
        version="0.1",
        source_citation=_fixture_citation(filename),
    )
    for filename in (
        "door_width.ids",
        "door_name_recorded.ids",
        "door_prohibited.ids",
        # T-0037: the zero-subject prohibited case -- unlike door_prohibited.ids (three
        # real doors are matched and prohibited), this specification's applicability
        # matches nothing at all in three_doors.ifc, which is the case that reads as a
        # PASS/INDETERMINATE contradiction unless the requirement row explains itself.
        "window_prohibited.ids",
        # T-0037 review round 2 (F1): a specification whose own applicability is never
        # established (declares ifcVersion="IFC2X3", three_doors.ifc is IFC4) while
        # ifctester still evaluates its requirement against three real, matched doors --
        # a genuine PASS that needs a caveat rather than reading as unqualified.
        "door_schema_mismatch.ids",
        # T-0039: the requirement's own attribute *name* is itself an `xs:restriction`
        # (an enumeration of two acceptable attribute names) rather than a literal
        # `ids:simpleValue` -- the fixture that reproduces the dict-repr subject line
        # this task exists to fix.
        "door_name_restricted.ids",
        # T-0039: a two-facet applicability (an Entity facet and an Attribute facet) --
        # the fixture that exercises the localized joiner between applicability facets,
        # replacing the engine's own hardcoded " and ".
        "door_width_named_applicability.ids",
        # T-0039 review, F1: the requirement's own name is restricted (as above) AND the
        # same facet carries a value bound -- the case `ifctester` evaluates
        # conjunctively rather than disjunctively, which the disjunctive rendering got
        # wrong before this fix. Pairs with `door_named_bound.ifc`.
        "door_name_restricted_with_bound.ids",
        # T-0039 review, F2: the applicability's Entity facet restricts predefinedType
        # to an enumeration rather than stating one literally -- the case the engine
        # used to collapse only `predefined_type`, leaving the literal `name` to state
        # an unrestricted template that overstated what the specification covers.
        "door_predefined_type_restricted.ids",
    )
)


class Command(BaseCommand):
    help = "Seed the rule pack catalogue from IDS files already in this repository."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002
        service = RulePackService()
        created = 0
        skipped = 0

        for entry in SEED_MANIFEST:
            ids_path = ENGINE_FIXTURES / entry.filename
            if not ids_path.is_file():
                raise CommandError(f"seed fixture not found: {ids_path}")

            pack, was_created = service.seed(
                ids_path=ids_path,
                jurisdiction=entry.jurisdiction,
                region=entry.region,
                version=entry.version,
                source_citation=entry.source_citation,
            )
            if was_created:
                created += 1
                self.stdout.write(
                    self.style.SUCCESS(f"created: {pack.name} ({pack.jurisdiction})")
                )
            else:
                skipped += 1
                self.stdout.write(
                    f"skipped (already seeded): {pack.name} ({pack.jurisdiction})"
                )

        total = RulePack.objects.count()
        self.stdout.write(
            f"done: {created} created, {skipped} skipped, "
            f"{total} rule packs in the catalogue"
        )
