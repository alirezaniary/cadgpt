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
from cadgpt_regulations.extraction_ingest import (
    ingest_extraction_response,
    ingest_validator_response,
)
from cadgpt_regulations.extraction_jobs import DEFAULT_MODEL, build_extraction_jobs
from cadgpt_regulations.extraction_status import build_extraction_status
from cadgpt_regulations.inventory import (
    build_inventory,
    ensure_output_outside_source,
    write_inventory,
)
from cadgpt_regulations.jsonio import (
    JsonObject,
    canonical_bytes,
    load_object,
    sha256_json,
)
from cadgpt_regulations.page_probe import build_page_probe, parse_page_range
from cadgpt_regulations.semantic_publish import (
    build_semantic_publication,
    validate_semantic_publication,
)
from cadgpt_regulations.storage import (
    ensure_private_tree,
    install_immutable_bytes,
    validate_output_root,
)
from cadgpt_regulations.structure import build_structure, validate_structure
from cadgpt_regulations.transcription import build_transcription
from cadgpt_regulations.transcription_check import check_transcription
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

    page_probe = subcommands.add_parser(
        "page-probe", help="build immutable native text and render evidence per PDF page"
    )
    page_probe.add_argument("--acquisition", type=Path, required=True)
    page_probe.add_argument("--root", type=Path, required=True)
    page_probe.add_argument("--output-root", type=Path, required=True)
    page_probe.add_argument("--catalog", type=Path)
    page_probe.add_argument("--catalog-key", action="append", default=[])
    page_probe.add_argument(
        "--pages",
        action="append",
        default=[],
        metavar="START-END",
        help="inclusive page range applied to each selected document",
    )
    page_probe.add_argument("--render-dpi", type=int, default=400)
    page_probe.add_argument("--tessdata", type=Path)
    page_probe.add_argument("--workers", type=int, default=1)
    page_probe.add_argument("--page-timeout", type=int, default=180)

    transcribe = subcommands.add_parser(
        "transcribe", help="build normalized text, OCR evidence, and model bundles"
    )
    transcribe.add_argument("--probe", type=Path, required=True)
    transcribe.add_argument("--root", type=Path, required=True)
    transcribe.add_argument("--tessdata", type=Path)
    transcribe.add_argument("--workers", type=int, default=1)
    transcribe.add_argument("--ocr-timeout", type=int, default=180)
    transcribe.add_argument("--bundle-max-pages", type=int, default=10)
    transcribe.add_argument("--bundle-max-bytes", type=int, default=8 * 1024 * 1024)

    transcription_check = subcommands.add_parser(
        "transcription-check", help="fail closed unless all page evidence re-attests"
    )
    transcription_check.add_argument("manifest", type=Path)
    transcription_check.add_argument("--root", type=Path, required=True)
    transcription_check.add_argument("--acquisition-root", type=Path, required=True)
    transcription_check.add_argument("--catalog", type=Path)

    structure = subcommands.add_parser(
        "structure", help="build source graphs and layered mathematical evidence"
    )
    structure.add_argument("--transcription", type=Path, required=True)
    structure.add_argument("--root", type=Path, required=True)
    structure.add_argument("--output-root", type=Path, required=True)

    structure_check = subcommands.add_parser(
        "structure-check", help="re-attest source graphs, anchors, and formula crops"
    )
    structure_check.add_argument("manifest", type=Path)
    structure_check.add_argument("--root", type=Path, required=True)
    structure_check.add_argument("--transcription", type=Path, required=True)
    structure_check.add_argument("--transcription-root", type=Path, required=True)

    extract_jobs = subcommands.add_parser(
        "extract-jobs", help="queue two blind Luna passes for every transcription bundle"
    )
    extract_jobs.add_argument("--transcription", type=Path, required=True)
    extract_jobs.add_argument("--root", type=Path, required=True)
    extract_jobs.add_argument("--output-root", type=Path, required=True)
    extract_jobs.add_argument("--model", default=DEFAULT_MODEL)

    extract_ingest = subcommands.add_parser(
        "extract-ingest", help="validate and durably ingest one blind Luna response"
    )
    extract_ingest.add_argument("--jobs", type=Path, required=True)
    extract_ingest.add_argument("--job-id", required=True)
    extract_ingest.add_argument("--response", type=Path, required=True)
    extract_ingest.add_argument("--transcription-root", type=Path, required=True)
    extract_ingest.add_argument("--output-root", type=Path, required=True)

    validator_ingest = subcommands.add_parser(
        "validator-ingest", help="ingest an independent decision over two blind passes"
    )
    validator_ingest.add_argument("--jobs", type=Path, required=True)
    validator_ingest.add_argument("--bundle-id", required=True)
    validator_ingest.add_argument("--response", type=Path, required=True)
    validator_ingest.add_argument("--transcription-root", type=Path, required=True)
    validator_ingest.add_argument("--output-root", type=Path, required=True)

    extraction_status = subcommands.add_parser(
        "extraction-status", help="reconstruct complete queue state from ingest receipts"
    )
    extraction_status.add_argument("--jobs", type=Path, required=True)
    extraction_status.add_argument("--output-root", type=Path, required=True)

    semantic_publish = subcommands.add_parser(
        "semantic-publish",
        help="publish accepted rules and separate every deferred semantic record",
    )
    semantic_publish.add_argument("--catalog", type=Path)
    semantic_publish.add_argument("--acquisition", type=Path)
    semantic_publish.add_argument("--acquisition-root", type=Path)
    semantic_publish.add_argument("--jobs", type=Path, required=True)
    semantic_publish.add_argument("--structure", type=Path, required=True)
    semantic_publish.add_argument("--extraction-root", type=Path, required=True)
    semantic_publish.add_argument("--structure-root", type=Path, required=True)
    semantic_publish.add_argument("--output-root", type=Path, required=True)

    semantic_publish_check = subcommands.add_parser(
        "semantic-publish-check",
        help="re-attest a structured semantic publication",
    )
    semantic_publish_check.add_argument("manifest", type=Path)
    semantic_publish_check.add_argument("--root", type=Path, required=True)

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
        if args.command == "page-probe":
            if args.workers < 1:
                raise AcquisitionError("page-probe workers must be at least one")
            receipt = _load_receipt(args.acquisition)
            catalog = load_catalog(args.catalog)
            run = build_page_probe(
                receipt,
                acquisition_root=args.root,
                output_root=args.output_root,
                catalog=catalog,
                catalog_keys=tuple(args.catalog_key),
                page_ranges=tuple(parse_page_range(value) for value in args.pages),
                render_dpi=args.render_dpi,
                tessdata_directory=args.tessdata,
                workers=args.workers,
                page_timeout_seconds=args.page_timeout,
            )
            summary = cast(JsonObject, run.manifest["summary"])
            print(f"wrote deterministic page probe: {run.manifest_path}")
            print(
                f"pages {summary['pages_ready']} ready, "
                f"{summary['pages_needs_review']} need review, "
                f"{summary['pages_failed']} failed; "
                f"packages {run.packages_created} created, {run.packages_reused} reused"
            )
            return int(
                cast(int, summary["pages_needs_review"]) > 0
                or cast(int, summary["pages_failed"]) > 0
            )
        if args.command == "transcribe":
            probe = _load_receipt(args.probe)
            transcription_run = build_transcription(
                probe,
                root=args.root,
                tessdata_directory=args.tessdata,
                workers=args.workers,
                ocr_timeout_seconds=args.ocr_timeout,
                bundle_max_pages=args.bundle_max_pages,
                bundle_max_bytes=args.bundle_max_bytes,
            )
            summary = cast(JsonObject, transcription_run.manifest["summary"])
            print(f"wrote deterministic transcription: {transcription_run.manifest_path}")
            print(
                f"pages {summary['pages_ready']} ready, "
                f"{summary['pages_needs_review']} need review, "
                f"{summary['pages_failed']} failed; "
                f"packages {transcription_run.packages_created} created, "
                f"{transcription_run.packages_reused} reused; bundles "
                f"{transcription_run.bundles_created} created, "
                f"{transcription_run.bundles_reused} reused"
            )
            return int(cast(int, summary["pages_failed"]) > 0)
        if args.command == "transcription-check":
            transcription = _load_receipt(args.manifest)
            check_run = check_transcription(
                transcription,
                root=args.root,
                acquisition_root=args.acquisition_root,
                catalog=load_catalog(args.catalog),
            )
            summary = cast(JsonObject, check_run.report["summary"])
            print(f"wrote transcription check: {check_run.report_path}")
            print(
                f"observed {summary['documents_observed']} documents and "
                f"{summary['pages_observed']} pages; "
                f"{summary['blockers']} blocker(s)"
            )
            if not check_run.report["valid"]:
                for blocker in cast(list[JsonObject], check_run.report["blockers"]):
                    print(
                        f"- {blocker['subject']}: {blocker['code']}: "
                        f"{blocker['diagnostic']}",
                        file=sys.stderr,
                    )
                return 1
            return 0
        if args.command == "structure":
            structure_run = build_structure(
                _load_receipt(args.transcription),
                transcription_root=args.root,
                output_root=args.output_root,
            )
            summary = cast(JsonObject, structure_run.manifest["summary"])
            print(f"wrote deterministic structure: {structure_run.manifest_path}")
            print(
                f"accounted {summary['documents']} documents and {summary['pages']} pages; "
                f"{summary['nodes']} nodes, {summary['tables']} tables, "
                f"{summary['formulas']} formulas, {summary['units']} units; "
                f"graphs {structure_run.graphs_created} created, "
                f"{structure_run.graphs_reused} reused"
            )
            return 0
        if args.command == "structure-check":
            manifest = _load_receipt(args.manifest)
            transcription = _load_receipt(args.transcription)
            validate_structure(
                manifest,
                root=args.root,
                transcription=transcription,
                transcription_root=args.transcription_root,
            )
            summary = cast(JsonObject, manifest["summary"])
            print(
                f"valid structure: {summary['documents']} documents, "
                f"{summary['pages']} pages, {summary['formulas']} formula candidates, "
                f"{summary['needs_review']} deferred review flags"
            )
            return 0
        if args.command == "extract-jobs":
            transcription = _load_receipt(args.transcription)
            queue = build_extraction_jobs(
                transcription,
                root=args.root,
                model=args.model,
            )
            validate_output_root(args.output_root, description="extraction output root")
            queue_install = install_immutable_bytes(
                args.output_root / "jobs.json", canonical_bytes(queue)
            )
            summary = cast(JsonObject, queue["summary"])
            print(
                f"extraction queue {queue_install.status}: {args.output_root / 'jobs.json'}"
            )
            print(
                f"queued {summary['jobs']} blind jobs for {summary['bundles']} bundles "
                f"across {summary['documents']} documents"
            )
            return 0
        if args.command == "extract-ingest":
            ingest_run = ingest_extraction_response(
                _load_receipt(args.jobs),
                job_id=args.job_id,
                response_path=args.response,
                transcription_root=args.transcription_root,
                output_root=args.output_root,
            )
            print(f"response {ingest_run.response_status}: {ingest_run.response_path}")
            print(
                f"{ingest_run.job_id}: {ingest_run.semantic.candidates} candidates, "
                f"{ingest_run.semantic.unique_span_references} unique source spans; "
                f"state {ingest_run.state}"
            )
            return 0
        if args.command == "validator-ingest":
            validator_run = ingest_validator_response(
                _load_receipt(args.jobs),
                bundle_id=args.bundle_id,
                response_path=args.response,
                transcription_root=args.transcription_root,
                output_root=args.output_root,
            )
            print(
                f"validator response {validator_run.response_status}: "
                f"{validator_run.response_path}"
            )
            print(
                f"{validator_run.validation_id}: "
                f"{validator_run.accepted_candidates} accepted, "
                f"{validator_run.deferred_candidates} deferred; "
                f"state {validator_run.state}"
            )
            return 0
        if args.command == "extraction-status":
            status = build_extraction_status(
                _load_receipt(args.jobs), output_root=args.output_root
            )
            digest = sha256_json(status)
            directory = ensure_private_tree(args.output_root, "status")
            path = directory / f"{digest}.json"
            status_install = install_immutable_bytes(path, canonical_bytes(status))
            summary = cast(JsonObject, status["summary"])
            print(f"extraction status {status_install.status}: {path}")
            print(
                f"jobs {summary['jobs_ingested']}/{summary['jobs']} ingested; bundles "
                f"{summary['bundles_accepted']} accepted, "
                f"{summary['bundles_needs_validation']} need validation, "
                f"{summary['bundles_pending']} pending"
            )
            return 0
        if args.command == "semantic-publish":
            publication = build_semantic_publication(
                load_catalog(args.catalog),
                _load_receipt(args.jobs),
                _load_receipt(args.structure),
                acquisition=(
                    None if args.acquisition is None else _load_receipt(args.acquisition)
                ),
                acquisition_root=args.acquisition_root,
                extraction_root=args.extraction_root,
                structure_root=args.structure_root,
                output_root=args.output_root,
            )
            summary = cast(JsonObject, publication.manifest["summary"])
            print(f"semantic publication: {publication.manifest_path}")
            print(
                f"{summary['rules']} accepted rules, {summary['formulas']} formulas, "
                f"{summary['tables']} tables, {summary['units']} units; "
                f"{summary['deferred']} deferred; complete "
                f"{str(publication.manifest['complete']).lower()}"
            )
            return 0
        if args.command == "semantic-publish-check":
            publication_manifest = _load_receipt(args.manifest)
            validate_semantic_publication(publication_manifest, root=args.root)
            summary = cast(JsonObject, publication_manifest["summary"])
            print(
                f"valid semantic publication: {summary['rules']} rules, "
                f"{summary['deferred']} deferred records"
            )
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
