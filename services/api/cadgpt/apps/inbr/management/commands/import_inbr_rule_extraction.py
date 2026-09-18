"""Import one source-bound provisional extraction into the INBR projection."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cadgpt.apps.inbr.rule_extraction_import import (
    RuleExtractionImportError,
    import_rule_extraction,
)


class Command(BaseCommand):
    help = "Import a provisional INBR extraction bound to a structured transcript."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--transcript", type=Path, required=True)
        parser.add_argument("--extraction", type=Path, required=True)
        parser.add_argument("--document-key", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *_args, **options) -> str:
        try:
            result = import_rule_extraction(
                options["transcript"], options["extraction"],
                document_key=options["document_key"], dry_run=options["dry_run"],
            )
        except RuleExtractionImportError as exc:
            raise CommandError(str(exc)) from exc
        mode = "validated" if result.dry_run else "imported"
        self.stdout.write(
            f"{mode} {result.candidates} candidates, "
            f"{result.no_assertions} no_assertion records"
        )
        return ""
