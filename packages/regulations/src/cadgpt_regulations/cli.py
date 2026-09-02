"""Inventory and gate a local regulation corpus from the terminal."""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path
from typing import cast

from cadgpt_regulations.acquisition import acquire_corpus, check_acquisition_health
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import AcquisitionError, RegulationsError
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

    acquire = subcommands.add_parser(
        "acquire", help="acquire and attest every configured official source"
    )
    acquire.add_argument("--output-root", type=Path, required=True)
    acquire.add_argument("--catalog", type=Path)

    acquisition_check = subcommands.add_parser(
        "acquisition-check", help="fail unless an acquisition receipt and storage are sound"
    )
    acquisition_check.add_argument("receipt", type=Path)
    acquisition_check.add_argument("--root", type=Path, required=True)
    acquisition_check.add_argument("--catalog", type=Path)

    validate = subcommands.add_parser("validate", help="validate a generated manifest")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--catalog", type=Path)

    publish = subcommands.add_parser(
        "publish-check", help="fail unless every artifact is safe to publish"
    )
    publish.add_argument("manifest", type=Path)
    publish.add_argument("--catalog", type=Path)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    _testing_allowed_origins: frozenset[str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inventory":
            ensure_output_outside_source(args.source, args.output)
            catalog = load_catalog(args.catalog)
            manifest = build_inventory(args.source, catalog=catalog)
            validate_manifest(manifest, catalog=catalog)
            write_inventory(manifest, args.output)
            _print_inventory_summary(manifest, args.output)
            return 0
        if args.command == "acquire":
            catalog = load_catalog(args.catalog)
            receipt = acquire_corpus(
                args.output_root,
                catalog=catalog,
                _testing_allowed_origins=_testing_allowed_origins,
            )
            _print_acquisition_summary(receipt, args.output_root / "acquisition.json")
            summary = cast(JsonObject, receipt["summary"])
            return int(
                summary["metadata_quarantined"] > 0 or summary["artifacts_quarantined"] > 0
            )
        if args.command == "acquisition-check":
            receipt = _load_receipt(args.receipt)
            catalog = load_catalog(args.catalog)
            acquisition_blockers = check_acquisition_health(
                receipt,
                catalog=catalog,
                root=args.root,
                _testing_allowed_origins=_testing_allowed_origins,
            )
            if not acquisition_blockers:
                summary = cast(JsonObject, receipt["summary"])
                print(
                    "valid acquisition: "
                    f"{summary['metadata_ready']}/{summary['metadata_expected']} metadata, "
                    f"{summary['artifacts_ready']}/{summary['artifacts_expected']} PDFs, "
                    f"{summary['pdf_pages']} pages, {summary['bytes']} bytes"
                )
                return 0
            print(
                f"invalid acquisition: {len(acquisition_blockers)} blocker(s)",
                file=sys.stderr,
            )
            for acquisition_blocker in acquisition_blockers:
                print(
                    f"- {acquisition_blocker.subject}: {acquisition_blocker.code}: "
                    f"{acquisition_blocker.diagnostic}",
                    file=sys.stderr,
                )
            return 1
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
        publish_blockers = check_publishable(manifest, catalog=catalog)
        if not publish_blockers:
            print("publishable: all expected artifacts are ready and reviewed")
            return 0
        print(f"not publishable: {len(publish_blockers)} blocker(s)", file=sys.stderr)
        for publish_blocker in publish_blockers:
            print(
                f"- {publish_blocker.local_path}: {publish_blocker.code}: "
                f"{publish_blocker.diagnostic}",
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


def _print_acquisition_summary(receipt: JsonObject, output: Path) -> None:
    summary = cast(JsonObject, receipt["summary"])
    print(f"wrote deterministic acquisition receipt: {output}")
    print(
        f"metadata {summary['metadata_ready']}/{summary['metadata_expected']} ready; "
        f"PDFs {summary['artifacts_ready']}/{summary['artifacts_expected']} ready"
    )
    print(
        f"acquired {summary['artifacts_acquired']}; reused {summary['artifacts_reused']}; "
        f"pages {summary['pdf_pages']}; bytes {summary['bytes']}; "
        f"quarantined {summary['artifacts_quarantined']}"
    )


def _load_receipt(path: Path) -> JsonObject:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise AcquisitionError(f"cannot inspect acquisition receipt {path}: {exc}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise AcquisitionError(f"acquisition receipt is not a regular file: {path}")
    return load_object(path, description="acquisition receipt")


if __name__ == "__main__":
    raise SystemExit(main())
