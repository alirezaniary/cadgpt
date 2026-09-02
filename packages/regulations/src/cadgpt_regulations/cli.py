"""Inventory and gate a local regulation corpus from the terminal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.inventory import (
    build_inventory,
    ensure_output_outside_source,
    write_inventory,
)
from cadgpt_regulations.jsonio import JsonObject, load_object
from cadgpt_regulations.validation import check_publishable, validate_manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadgpt-regulations",
        description="Build and validate deterministic regulation corpus inventories.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    inventory = subcommands.add_parser(
        "inventory", help="inventory a local artifact directory"
    )
    inventory.add_argument("source", type=Path)
    inventory.add_argument("--output", type=Path, required=True)
    inventory.add_argument("--catalog", type=Path)

    validate = subcommands.add_parser("validate", help="validate a generated manifest")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--catalog", type=Path)

    publish = subcommands.add_parser(
        "publish-check", help="fail unless every artifact is safe to publish"
    )
    publish.add_argument("manifest", type=Path)
    publish.add_argument("--catalog", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            ensure_output_outside_source(args.source, args.output)
            catalog = load_catalog(args.catalog)
            manifest = build_inventory(args.source, catalog=catalog)
            validate_manifest(manifest)
            write_inventory(manifest, args.output)
            _print_inventory_summary(manifest, args.output)
            return 0
        manifest = load_object(args.manifest, description="manifest")
        catalog = load_catalog(args.catalog)
        if args.command == "validate":
            validate_manifest(manifest, catalog=catalog)
            summary = cast(JsonObject, manifest["summary"])
            print(
                "valid manifest: "
                f"{summary['files_discovered']} files, "
                f"{summary['valid_pdfs']} valid PDFs, "
                f"{summary['pdf_pages']} PDF pages, "
                f"{summary['quarantined']} quarantined"
            )
            return 0
        blockers = check_publishable(manifest, catalog=catalog)
        if not blockers:
            print("publishable: all expected artifacts are ready and reviewed")
            return 0
        print(f"not publishable: {len(blockers)} blocker(s)", file=sys.stderr)
        for blocker in blockers:
            print(
                f"- {blocker.filename}: {blocker.code}: {blocker.diagnostic}",
                file=sys.stderr,
            )
        return 1
    except RegulationsError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _print_inventory_summary(manifest: JsonObject, output: Path) -> None:
    summary = cast(JsonObject, manifest["summary"])
    print(f"wrote deterministic manifest: {output}")
    print(
        f"accounted {summary['artifacts_accounted']}/{summary['expected_artifacts']} "
        f"expected artifacts across {summary['files_discovered']} files"
    )
    print(
        f"valid PDFs {summary['valid_pdfs']}; PDF pages {summary['pdf_pages']}; "
        f"quarantined {summary['quarantined']}; missing {summary['missing']}; "
        f"unaccounted {summary['unaccounted']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
