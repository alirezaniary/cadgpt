"""Inventory and gate a local regulation corpus from the terminal."""

from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path
from typing import cast

from cadgpt_regulations.acquisition import (
    acquire_corpus,
    check_acquisition_health,
    validate_acquisition_receipt,
)
from cadgpt_regulations.candidate_to_rule_ir import build_candidate_to_rule_ir_batch
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.errors import AcquisitionError, RegulationsError
from cadgpt_regulations.extraction_ingest import (
    ingest_extraction_response,
    ingest_validator_response,
)
from cadgpt_regulations.extraction_jobs import (
    DEFAULT_MODEL,
    build_structured_extraction_jobs,
)
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
    loads_object,
    sha256_json,
)
from cadgpt_regulations.luna_transcript import (
    build_luna_transcript_jobs,
    get_next,
    mark_failed,
    mark_finished,
    mark_started,
    reclaim_luna_chunk_from_ledger,
)
from cadgpt_regulations.page_probe import build_page_probe, parse_page_range
from cadgpt_regulations.provisional_batch import (
    build_provisional_batch,
    validate_provisional_batch,
)
from cadgpt_regulations.provisional_rule import (
    make_candidate_citation,
    make_provisional_rule,
    make_transcript_revision,
)
from cadgpt_regulations.rule_compiler import compile_native_attribute_rule
from cadgpt_regulations.rule_release import (
    build_rule_release_manifest,
    write_rule_release,
)
from cadgpt_regulations.semantic_publish import (
    build_semantic_publication,
    validate_semantic_publication,
)
from cadgpt_regulations.source_reanchor import reanchor_transcript
from cadgpt_regulations.storage import (
    ensure_private_tree,
    install_immutable_bytes,
    validate_output_root,
)
from cadgpt_regulations.structure import build_structure, validate_structure
from cadgpt_regulations.transcript_assembly import (
    audit_luna_transcripts,
    install_assembled_transcripts,
)
from cadgpt_regulations.transcription import build_transcription
from cadgpt_regulations.transcription_check import check_transcription
from cadgpt_regulations.validation import check_publishable, validate_manifest
from cadgpt_regulations.workspace import initialize_workspace


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadgpt-regulations",
        description="Build and validate deterministic regulation corpus inventories.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    workspace = subcommands.add_parser(
        "workspace", help="create and attest a durable private INBR workspace"
    )
    workspace.add_argument("--root", type=Path, required=True)

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
    page_probe.add_argument("--paddle-device", default="gpu:0")
    page_probe.add_argument("--workers", type=int, default=1)
    page_probe.add_argument("--page-timeout", type=int, default=180)

    transcribe = subcommands.add_parser(
        "transcribe", help="build normalized text, OCR evidence, and model bundles"
    )
    transcribe.add_argument("--probe", type=Path, required=True)
    transcribe.add_argument("--root", type=Path, required=True)
    transcribe.add_argument("--paddle-device", default="gpu:0")
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

    transcript_jobs = subcommands.add_parser(
        "transcript-jobs",
        help="queue independent Luna jobs for Persian structured transcripts",
    )
    transcript_jobs.add_argument("--transcription", type=Path, required=True)
    transcript_jobs.add_argument("--transcription-root", type=Path, required=True)
    transcript_jobs.add_argument("--acquisition-root", type=Path, required=True)
    transcript_jobs.add_argument("--output-root", type=Path, required=True)
    transcript_jobs.add_argument("--model", default="gpt-5.6-luna")

    get_next_parser = subcommands.add_parser(
        "get-next", help="return the next pending Luna chunks without mutation"
    )
    get_next_parser.add_argument("--jobs", type=Path, required=True)
    get_next_parser.add_argument("--output-root", type=Path, required=True)
    get_next_parser.add_argument("--max-workers", type=int, default=1)

    mark_started_parser = subcommands.add_parser(
        "mark-started", help="atomically lease pending Luna chunks"
    )
    mark_started_parser.add_argument("--jobs", type=Path, required=True)
    mark_started_parser.add_argument("--output-root", type=Path, required=True)
    mark_started_parser.add_argument("--worker-id", required=True)
    mark_started_parser.add_argument("--max-workers", type=int, default=1)

    mark_finished_parser = subcommands.add_parser(
        "mark-finished", help="persist a Luna response and mark its chunk complete"
    )
    mark_finished_parser.add_argument("--jobs", type=Path, required=True)
    mark_finished_parser.add_argument("--output-root", type=Path, required=True)
    mark_finished_parser.add_argument("--job-id", required=True)
    mark_finished_parser.add_argument("--worker-id", required=True)
    mark_finished_parser.add_argument("--lease-token", required=True)
    mark_finished_parser.add_argument("--response", type=Path, required=True)

    mark_failed_parser = subcommands.add_parser(
        "mark-failed", help="record a failed Luna chunk attempt"
    )
    mark_failed_parser.add_argument("--jobs", type=Path, required=True)
    mark_failed_parser.add_argument("--output-root", type=Path, required=True)
    mark_failed_parser.add_argument("--job-id", required=True)
    mark_failed_parser.add_argument("--worker-id", required=True)
    mark_failed_parser.add_argument("--lease-token", required=True)
    mark_failed_parser.add_argument("--error", required=True)

    reclaim_parser = subcommands.add_parser(
        "reclaim", help="reclaim a leased Luna chunk after interruption"
    )
    reclaim_parser.add_argument("--jobs", type=Path, required=True)
    reclaim_parser.add_argument("--output-root", type=Path, required=True)
    reclaim_parser.add_argument("--job-id", required=True)

    assemble_parser = subcommands.add_parser(
        "assemble-transcripts", help="audit and assemble completed Persian Luna transcripts"
    )
    assemble_parser.add_argument("--jobs", type=Path, required=True)
    assemble_parser.add_argument("--ledger", type=Path, required=True)
    assemble_parser.add_argument("--acquisition", type=Path, required=True)
    assemble_parser.add_argument("--acquisition-root", type=Path, required=True)
    assemble_parser.add_argument("--output-root", type=Path, required=True)
    assemble_parser.add_argument("--audit-only", action="store_true")

    extract_jobs = subcommands.add_parser(
        "extract-jobs", help="queue two blind Luna passes for every structured bundle"
    )
    extract_jobs.add_argument("--transcription", type=Path, required=True)
    extract_jobs.add_argument("--root", type=Path, required=True)
    extract_jobs.add_argument(
        "--structure",
        type=Path,
        required=True,
        help="validated T-0027 structure manifest; binds jobs to source blocks",
    )
    extract_jobs.add_argument(
        "--structure-root",
        type=Path,
        required=True,
        help="root containing attested source graphs",
    )
    extract_jobs.add_argument("--output-root", type=Path, required=True)
    extract_jobs.add_argument("--model", default=DEFAULT_MODEL)

    extract_ingest = subcommands.add_parser(
        "extract-ingest", help="validate and durably ingest one blind Luna response"
    )
    extract_ingest.add_argument("--jobs", type=Path, required=True)
    extract_ingest.add_argument("--job-id", required=True)
    extract_ingest.add_argument("--response", type=Path, required=True)
    extract_ingest.add_argument("--transcription-root", type=Path, required=True)
    extract_ingest.add_argument("--structure-root", type=Path, required=True)
    extract_ingest.add_argument("--output-root", type=Path, required=True)

    validator_ingest = subcommands.add_parser(
        "validator-ingest", help="ingest an independent decision over two blind passes"
    )
    validator_ingest.add_argument("--jobs", type=Path, required=True)
    validator_ingest.add_argument("--bundle-id", required=True)
    validator_ingest.add_argument("--response", type=Path, required=True)
    validator_ingest.add_argument("--transcription-root", type=Path, required=True)
    validator_ingest.add_argument("--structure-root", type=Path, required=True)
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

    compile_native = subcommands.add_parser(
        "compile-native-rule",
        help="compile one citation-bearing native IDS rule from canonical rule IR",
    )
    compile_native.add_argument("--rule", type=Path, required=True)
    compile_native.add_argument("--output-root", type=Path, required=True)
    compile_native.add_argument("--compiler-version", default="native-ids-1.0.0")

    provisional = subcommands.add_parser(
        "provisional-rule",
        help="create a sandbox rule candidate from an existing Persian transcript",
    )
    provisional.add_argument("--transcript", type=Path, required=True)
    provisional.add_argument("--rule", type=Path, required=True)
    provisional.add_argument("--output-root", type=Path, required=True)
    provisional.add_argument("--revision", required=True)
    provisional.add_argument("--edition", required=True)
    provisional.add_argument("--table-index", type=int, default=0)
    provisional.add_argument("--printed-page-label")
    provisional.add_argument(
        "--state", choices=("candidate", "needs_review"), default="candidate"
    )

    provisional_batch = subcommands.add_parser(
        "provisional-batch",
        help="persist a batch of sandbox candidates from one structured transcript",
    )
    provisional_batch.add_argument("--transcript", type=Path, required=True)
    provisional_batch.add_argument("--extraction", type=Path, required=True)
    provisional_batch.add_argument("--output-root", type=Path, required=True)
    provisional_batch.add_argument("--revision", required=True)
    provisional_batch.add_argument("--edition", required=True)

    candidate_to_rule_ir = subcommands.add_parser(
        "candidate-to-rule-ir",
        help="join provisional candidates to a verified citation and an IFC mapping",
    )
    candidate_to_rule_ir.add_argument(
        "--batch-root",
        type=Path,
        required=True,
        help="output root written by one or more provisional-batch runs",
    )
    candidate_to_rule_ir.add_argument("--mapping", type=Path, required=True)
    candidate_to_rule_ir.add_argument("--output-root", type=Path, required=True)

    reanchor = subcommands.add_parser(
        "reanchor-transcript",
        help="optionally audit a Persian transcript against T-0027 source graph spans",
    )
    reanchor.add_argument("--transcript", type=Path, required=True)
    reanchor.add_argument("--graph", type=Path, required=True)
    reanchor.add_argument("--output-root", type=Path, required=True)

    rule_release = subcommands.add_parser(
        "rule-release",
        help="package compiled IDS rules into a hash-pinned release",
    )
    rule_release.add_argument(
        "--rules-root",
        type=Path,
        required=True,
        help="root containing compiled rules/*/rule.ids and rule.json",
    )
    rule_release.add_argument("--output-root", type=Path, required=True)
    rule_release.add_argument("--deferred", type=Path)
    rule_release.add_argument("--assertions", type=Path)

    validate = subcommands.add_parser("validate", help="validate a generated manifest")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--catalog", type=Path)

    publish = subcommands.add_parser(
        "publish-check", help="fail unless every artifact is safe to publish"
    )
    publish.add_argument("manifest", type=Path)
    publish.add_argument("--catalog", type=Path)
    return parser


def _resolve_root_arguments(args: argparse.Namespace) -> None:
    """Make every "*root" path argument absolute, in place.

    `tempfile.mkdtemp()` always returns an absolute path even when given a relative
    `dir=`. Every "*root" argument is later combined with that absolute temporary
    directory and compared for sibling identity (see storage.install_terminal_directory),
    so a relative root fails that comparison even when the paths are really siblings.
    Normalizing every root-style path here, once, at the CLI boundary avoids that class
    of bug for every subcommand rather than patching each comparison site.
    """
    for name, value in vars(args).items():
        if "root" in name and isinstance(value, Path):
            # Make sibling comparisons absolute without following symlinks;
            # storage's no-symlink attestation must still see the original path.
            setattr(args, name, value.absolute())


def _load_compiled_rule_artifacts(root: Path) -> list[dict[str, object]]:
    """Load exactly one IDS and sidecar pair from each compiled rule directory."""
    rules_root = root / "rules"
    if not rules_root.is_dir():
        raise RegulationsError(f"compiled rules root has no rules directory: {rules_root}")
    compiled: list[dict[str, object]] = []
    for directory in sorted(path for path in rules_root.iterdir() if path.is_dir()):
        ids_path = directory / "rule.ids"
        sidecar_path = directory / "rule.json"
        if not ids_path.is_file() or not sidecar_path.is_file():
            raise RegulationsError(f"compiled rule is missing IDS or sidecar: {directory}")
        compiled.append(
            {
                "rule_id": directory.name,
                "ids_xml": ids_path.read_bytes(),
                "sidecar": load_object(sidecar_path, description="compiled rule sidecar"),
            }
        )
    if not compiled:
        raise RegulationsError("compiled rules root contains no rule directories")
    return compiled


def _load_batch_root(batch_root: Path) -> tuple[list[JsonObject], list[JsonObject]]:
    """Load every candidate and transcript revision written by provisional-batch.

    ``--batch-root`` accumulates across one or more ``provisional-batch`` runs
    (one per chunk); this reads everything present rather than one chunk's batch
    file, since candidates and revisions are content-addressed and safe to union.
    """
    candidates_root = batch_root / "candidates"
    revisions_root = batch_root / "transcript-revisions"
    if not candidates_root.is_dir() or not revisions_root.is_dir():
        raise RegulationsError(
            f"batch root is missing candidates/ or transcript-revisions/: {batch_root}"
        )
    candidates = [
        load_object(path, description="provisional candidate")
        for path in sorted(candidates_root.glob("*.json"))
    ]
    revisions = [
        load_object(path, description="transcript revision")
        for path in sorted(revisions_root.glob("*.json"))
    ]
    if not candidates:
        raise RegulationsError(f"batch root has no candidates: {batch_root}")
    return candidates, revisions


def _load_jsonl_records(path: Path) -> list[JsonObject]:
    records: list[JsonObject] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        records.append(loads_object(line, description=f"{path.name} record {line_number}"))
    return records


def main(
    argv: list[str] | None = None,
    *,
    _testing_allowed_origins: frozenset[str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    _resolve_root_arguments(args)
    try:
        if args.command == "workspace":
            stages = initialize_workspace(args.root)
            print(f"ready durable INBR workspace: {args.root}")
            print("stages " + ", ".join(stage.name for stage in stages))
            return 0
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
                paddle_device=args.paddle_device,
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
                paddle_device=args.paddle_device,
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
                f"{summary['formulas']} formulas, {summary['units']} units, "
                f"{summary['abbreviations']} abbreviations; "
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
                f"{summary['abbreviations']} abbreviations, "
                f"{summary['needs_review']} deferred review flags"
            )
            return 0
        if args.command == "transcript-jobs":
            queue = build_luna_transcript_jobs(
                _load_receipt(args.transcription),
                transcription_root=args.transcription_root,
                acquisition_root=args.acquisition_root,
                model=args.model,
            )
            validate_output_root(args.output_root, description="transcript output root")
            queue_path = args.output_root / "jobs.json"
            queue_install = install_immutable_bytes(queue_path, canonical_bytes(queue))
            summary = cast(JsonObject, queue["summary"])
            print(f"Luna transcript queue {queue_install.status}: {queue_path}")
            print(
                f"queued {summary['jobs']} deterministic chunks; "
                "workers return Persian structured transcripts"
            )
            return 0
        if args.command == "get-next":
            chunks = get_next(
                _load_receipt(args.jobs),
                output_root=args.output_root,
                max_workers=args.max_workers,
            )
            print(json.dumps({"chunks": list(chunks)}, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "mark-started":
            result = mark_started(
                _load_receipt(args.jobs),
                output_root=args.output_root,
                worker_id=args.worker_id,
                max_workers=args.max_workers,
            )
            print(
                json.dumps(
                    {"claims": [claim.__dict__ for claim in result.claims]},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "mark-finished":
            result = mark_finished(
                _load_receipt(args.jobs),
                output_root=args.output_root,
                job_id=args.job_id,
                worker_id=args.worker_id,
                lease_token=args.lease_token,
                response_path=args.response,
            )
            print(f"Luna chunk completed: {args.job_id}")
            if result.structured_transcript_path is not None:
                print(f"Persian structured transcript: {result.structured_transcript_path}")
            return 0
        if args.command == "mark-failed":
            ledger = mark_failed(
                _load_receipt(args.jobs),
                output_root=args.output_root,
                job_id=args.job_id,
                worker_id=args.worker_id,
                lease_token=args.lease_token,
                error=args.error,
            )
            print(f"Luna chunk failed: {args.job_id}; state {ledger['summary']}")
            return 0
        if args.command == "reclaim":
            ledger = reclaim_luna_chunk_from_ledger(
                _load_receipt(args.jobs),
                output_root=args.output_root,
                job_id=args.job_id,
            )
            print(f"Luna chunk reclaimed: {args.job_id}; state {ledger['summary']}")
            return 0
        if args.command == "assemble-transcripts":
            queue = _load_receipt(args.jobs)
            ledger = _load_receipt(args.ledger)
            acquisition = _load_receipt(args.acquisition)
            validate_acquisition_receipt(acquisition, root=args.acquisition_root)
            report, books = audit_luna_transcripts(
                queue,
                ledger,
                acquisition,
                output_root=args.output_root,
                acquisition_root=args.acquisition_root,
            )
            if args.audit_only or not report["complete"]:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
                return 0 if args.audit_only else 1
            path = install_assembled_transcripts(
                report, books, output_root=args.output_root
            )
            print(f"assembled Persian transcripts: {path}")
            return 0
        if args.command == "extract-jobs":
            transcription = _load_receipt(args.transcription)
            queue = build_structured_extraction_jobs(
                transcription,
                root=args.root,
                model=args.model,
                structure=_load_receipt(args.structure),
                structure_root=args.structure_root,
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
                structure_root=args.structure_root,
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
                structure_root=args.structure_root,
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
                f"{summary['bundles_needs_review']} need review, "
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
        if args.command == "reanchor-transcript":
            result = reanchor_transcript(
                load_object(args.transcript, description="structured transcript"),
                load_object(args.graph, description="source graph"),
            )
            validate_output_root(args.output_root, description="re-anchor output root")
            directory = ensure_private_tree(args.output_root, "reanchored")
            transcript_path = directory / "transcript.json"
            report_path = directory / "report.json"
            transcript_install = install_immutable_bytes(
                transcript_path, canonical_bytes(result.transcript)
            )
            report_install = install_immutable_bytes(
                report_path, canonical_bytes(result.report)
            )
            summary = cast(JsonObject, result.report["summary"])
            print(f"re-anchored transcript {transcript_install.status}: {transcript_path}")
            print(f"re-anchor report {report_install.status}: {report_path}")
            print(
                f"{summary['anchored']} anchored, {summary['ambiguous']} ambiguous, "
                f"{summary['unmatched']} unmatched; publishable "
                f"{str(summary['publishable']).lower()}"
            )
            return 0 if summary["publishable"] else 1
        if args.command == "compile-native-rule":
            rule = load_object(args.rule, description="canonical rule")
            compiled = compile_native_attribute_rule(
                rule, compiler_version=args.compiler_version
            )
            validate_output_root(args.output_root, description="rule output root")
            directory = ensure_private_tree(args.output_root, f"rules/{compiled.rule_id}")
            ids_path = directory / "rule.ids"
            sidecar_path = directory / "rule.json"
            ids_install = install_immutable_bytes(ids_path, compiled.ids_xml)
            sidecar_install = install_immutable_bytes(
                sidecar_path, canonical_bytes(compiled.sidecar)
            )
            print(f"compiled IDS {ids_install.status}: {ids_path}")
            print(f"compiled rule sidecar {sidecar_install.status}: {sidecar_path}")
            return 0
        if args.command == "provisional-rule":
            transcript = load_object(args.transcript, description="Persian transcript")
            rule = load_object(args.rule, description="provisional rule")
            source = transcript.get("source")
            tables = transcript.get("tables")
            if not isinstance(source, dict) or not isinstance(tables, list):
                raise RegulationsError("transcript must contain source and tables")
            if args.table_index < 0 or args.table_index >= len(tables):
                raise RegulationsError("table index is outside transcript tables")
            table = tables[args.table_index]
            if not isinstance(table, dict) or not isinstance(table.get("text_fa"), str):
                raise RegulationsError("selected transcript table has no Persian text")
            page_ids = table.get("source_page_ids")
            page_id = page_ids[0] if isinstance(page_ids, list) and page_ids else None
            revision = make_transcript_revision(
                document_key=str(source["catalog_key"]),
                revision=args.revision,
                transcript_fa=table["text_fa"],
                pdf_page=int(source["start_pdf_page"]),
                printed_page_label=args.printed_page_label,
                page_id=page_id,
                source_document_sha256=str(source["source_sha256"]),
                transcript_payload=transcript,
            )
            citation = make_candidate_citation(
                transcript_revision=revision,
                book_title_fa=str(transcript.get("title_fa", source["catalog_key"])),
                edition_fa=args.edition,
                citation_status=args.state,
            )
            candidate = make_provisional_rule(
                rule=rule,
                transcript_revision=revision,
                state=args.state,
                candidate_citation=citation,
                review_flags=["TRANSCRIPT_REVIEW_PENDING"],
            )
            validate_output_root(
                args.output_root, description="provisional rule output root"
            )
            revision_path = (
                ensure_private_tree(args.output_root, "transcript-revisions")
                / f"{revision['revision_id']}.json"
            )
            candidate_path = ensure_private_tree(args.output_root, "candidates") / (
                f"{candidate['candidate_id']}.json"
            )
            install_immutable_bytes(revision_path, canonical_bytes(revision))
            install_immutable_bytes(candidate_path, canonical_bytes(candidate))
            print(f"transcript revision: {revision_path}")
            print(f"sandbox candidate: {candidate_path}")
            return 0
        if args.command == "provisional-batch":
            transcript = load_object(args.transcript, description="Persian transcript")
            extraction = load_object(args.extraction, description="rule extraction")
            batch = build_provisional_batch(
                transcript,
                extraction,
                revision=args.revision,
                edition_fa=args.edition,
            )
            validate_provisional_batch(batch)
            validate_output_root(args.output_root, description="provisional batch root")
            revisions_root = ensure_private_tree(args.output_root, "transcript-revisions")
            candidates_root = ensure_private_tree(args.output_root, "candidates")
            extractions_root = ensure_private_tree(args.output_root, "extractions")
            extraction_hash = sha256_json(extraction)
            install_immutable_bytes(
                extractions_root / f"{extraction_hash}.json",
                canonical_bytes(extraction),
            )
            for revision in cast(list[JsonObject], batch["transcript_revisions"]):
                install_immutable_bytes(
                    revisions_root / f"{revision['revision_id']}.json",
                    canonical_bytes(revision),
                )
            records = []
            for candidate in cast(list[JsonObject], batch["candidates"]):
                install_immutable_bytes(
                    candidates_root / f"{candidate['candidate_id']}.json",
                    canonical_bytes(candidate),
                )
                records.append(candidate["candidate_id"])
            batch_path = args.output_root / f"batch-{batch['batch_id']}.json"
            install_immutable_bytes(batch_path, canonical_bytes(batch))
            print(f"provisional batch: {batch_path}")
            print(f"candidates: {len(records)}")
            return 0
        if args.command == "candidate-to-rule-ir":
            candidates, revisions = _load_batch_root(args.batch_root)
            mapping = load_object(args.mapping, description="IFC target mapping")
            join_outcome = build_candidate_to_rule_ir_batch(candidates, revisions, mapping)
            validate_output_root(args.output_root, description="rule IR output root")
            rules_root = ensure_private_tree(args.output_root, "rules")
            for rule_ir in cast(list[JsonObject], join_outcome["mapped"]):
                citation = cast(JsonObject, rule_ir["source_citation"])
                document_directory = ensure_private_tree(
                    rules_root, cast(str, citation["document_key"])
                )
                install_immutable_bytes(
                    document_directory / f"{rule_ir['rule_key']}.json",
                    canonical_bytes(rule_ir),
                )
            unmapped_path = args.output_root / "unmapped.json"
            install_immutable_bytes(
                unmapped_path,
                canonical_bytes(cast(JsonObject, {"unmapped": join_outcome["unmapped"]})),
            )
            summary = cast(JsonObject, join_outcome["summary"])
            print(f"candidate-to-rule-ir rules: {rules_root}")
            print(f"candidate-to-rule-ir unmapped: {unmapped_path}")
            print(
                f"{summary['candidates']} candidates, {summary['mapped']} mapped, "
                f"{summary['unmapped']} unmapped"
            )
            return 0
        if args.command == "rule-release":
            compiled = _load_compiled_rule_artifacts(args.rules_root)
            deferred = [] if args.deferred is None else _load_jsonl_records(args.deferred)
            assertion_count = 0
            if args.assertions is not None:
                assertion_payload = load_object(
                    args.assertions, description="assertion relations"
                )
                raw_assertions = assertion_payload.get("assertions")
                if not isinstance(raw_assertions, list):
                    raise RegulationsError("assertion relations has no assertions list")
                assertion_count = len(raw_assertions)
            manifest = build_rule_release_manifest(
                compiled,
                deferred_records=deferred,
                assertion_count=assertion_count,
            )
            release_directory = write_rule_release(
                manifest, compiled, output_root=args.output_root
            )
            print(f"rule release: {release_directory}")
            print(
                f"{manifest['coverage']['rules']} rules, "
                f"{manifest['coverage']['assertions']} assertions, "
                f"{manifest['coverage']['deferred']} deferred"
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
