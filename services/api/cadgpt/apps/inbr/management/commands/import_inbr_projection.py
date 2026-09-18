"""Import the immutable INBR transcript artifacts into the queryable projection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cadgpt.apps.inbr.models import PdfDocument, PdfPage

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DOCUMENT_RE = re.compile(r"^volume-(\d+)-edition-(\d+)$")


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CommandError(f"JSON root is not an object: {path}")
    return value


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_optional(root: Path, relative: str | None) -> str | None:
    if not relative:
        return None
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CommandError(f"cannot read evidence file {path}: {exc}") from exc


def _read_json_optional(root: Path, relative: str | None) -> Any:
    raw = _read_optional(root, relative)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CommandError(
            f"evidence JSON is invalid: {root / str(relative)}: {exc}"
        ) from exc


def _assembled_books(manifest: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    if manifest.get("complete") is not True:
        raise CommandError("assembled manifest is not complete")
    references = manifest.get("books")
    if not isinstance(references, list) or not references:
        raise CommandError("assembled manifest has no books")
    books: list[dict[str, Any]] = []
    for reference in references:
        if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
            raise CommandError("assembled manifest contains an invalid book reference")
        book = _load(root / str(reference["path"]))
        if book.get("complete") is not True:
            raise CommandError(f"assembled book is incomplete: {reference['path']}")
        books.append(book)
    return books


def _page_evidence(extraction_root: Path) -> dict[tuple[str, int], dict[str, Any]]:
    jobs = _load(extraction_root / "jobs.json").get("jobs")
    if not isinstance(jobs, list):
        raise CommandError("extraction jobs has no jobs list")
    result: dict[tuple[str, int], dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        for page in job.get("pages", []):
            if not isinstance(page, dict):
                raise CommandError("extraction job contains an invalid page")
            key = (str(job.get("catalog_key")), int(page["pdf_page"]))
            result.setdefault(key, page)
    return result


def _response_map(
    books: list[dict[str, Any]], root: Path
) -> dict[tuple[str, int], tuple[str, str, str]]:
    result: dict[tuple[str, int], tuple[str, str, str]] = {}
    for book in books:
        source = book["source"]
        key = str(source["catalog_key"])
        for chunk in sorted(book.get("chunks", []), key=lambda item: item["chunk_order"]):
            response_path = chunk.get("response_path")
            response_hash = chunk.get("response_sha256")
            if not isinstance(response_path, str) or not isinstance(response_hash, str):
                raise CommandError(
                    f"chunk {chunk.get('chunk_order')} has no response identity"
                )
            response_file = root / response_path
            try:
                actual_hash = hashlib.sha256(response_file.read_bytes()).hexdigest()
            except OSError as exc:
                raise CommandError(
                    f"cannot read Luna response {response_file}: {exc}"
                ) from exc
            if actual_hash != response_hash:
                raise CommandError(f"Luna response hash mismatch: {response_file}")
            for page in book["pages"]:
                if page["chunk_order"] != chunk["chunk_order"]:
                    continue
                result.setdefault(
                    (key, int(page["pdf_page"])),
                    (f"cas://sha256/{response_hash}", response_hash, response_path),
                )
    return result


class Command(BaseCommand):
    help = "Import complete INBR transcripts into the page-first PostgreSQL projection."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--transcription-manifest", type=Path, required=True)
        parser.add_argument("--transcription-root", type=Path, required=True)
        parser.add_argument("--assembled-manifest", type=Path, required=True)
        parser.add_argument("--assembled-root", type=Path, required=True)
        parser.add_argument("--extraction-root", type=Path, required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *_args, **options) -> str:
        transcription = _load(options["transcription_manifest"])
        assembled_manifest = _load(options["assembled_manifest"])
        transcription_root: Path = options["transcription_root"]
        books = _assembled_books(assembled_manifest, options["assembled_root"])
        response_map = _response_map(books, options["assembled_root"])
        evidence_map = _page_evidence(options["extraction_root"])
        source_documents = {
            item.get("catalog_key"): item
            for item in transcription.get("documents", [])
            if isinstance(item, dict)
        }
        if len(source_documents) != len(books):
            raise CommandError("assembled books and transcription documents do not match")

        documents: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        seen_pages: set[tuple[str, int]] = set()
        for book in books:
            source = book.get("source")
            if not isinstance(source, dict):
                raise CommandError("assembled book has no source")
            key = source.get("catalog_key")
            source_sha = source.get("sha256")
            document = source_documents.get(key)
            if (
                not isinstance(key, str)
                or not isinstance(source_sha, str)
                or not HASH_RE.fullmatch(source_sha)
            ):
                raise CommandError("assembled book has invalid document identity")
            if (
                not isinstance(document, dict)
                or document.get("source_sha256") != source_sha
            ):
                raise CommandError(f"source identity mismatch for {key}")
            match = DOCUMENT_RE.fullmatch(key)
            volume = int(match.group(1)) if match else None
            edition = int(match.group(2)) if match else None
            documents.append(
                {
                    "document_key": key,
                    "pdf_name": Path(str(document.get("artifact_path", f"{key}.pdf"))).name,
                    "file_path": str(
                        document.get("artifact_path", f"cas://sha256/{source_sha}")
                    ),
                    "storage_uri": f"cas://sha256/{source_sha}",
                    "volume_number": volume,
                    "edition_year": edition,
                    "edition_code": f"edition-{edition}" if edition else "unknown",
                    "title_fa": None,
                    "source_sha256": source_sha,
                    "file_size_bytes": document.get("source_bytes"),
                    "page_count": document.get("pdf_page_count"),
                    "metadata": {"catalog_order": document.get("catalog_order")},
                }
            )
            manifest_pages = {
                p.get("pdf_page"): p
                for p in document.get("pages", [])
                if isinstance(p, dict)
            }
            for item in book.get("pages", []):
                if not isinstance(item, dict):
                    raise CommandError(f"invalid page in assembled book {key}")
                page_number = item.get("pdf_page")
                page_id = item.get("page_id")
                text_fa = item.get("text_fa")
                source_page = manifest_pages.get(page_number)
                if (
                    not isinstance(page_number, int)
                    or not isinstance(page_id, str)
                    or not isinstance(text_fa, str)
                ):
                    raise CommandError(f"invalid transcript page in {key}")
                if (
                    not isinstance(source_page, dict)
                    or source_page.get("page_id") != page_id
                ):
                    raise CommandError(f"page identity mismatch for {key}:{page_number}")
                page_key = (key, page_number)
                if page_key in seen_pages:
                    raise CommandError(f"duplicate page {key}:{page_number}")
                seen_pages.add(page_key)
                evidence_page = evidence_map.get((key, page_number))
                if evidence_page is None:
                    raise CommandError(f"no evidence page for {key}:{page_number}")
                route = {
                    "none": "blank",
                    "native": "native",
                    "ocr": "paddle",
                    "native_plus_ocr": "native_plus_paddle",
                }.get(source_page.get("route"), "pending")
                native_text = _read_optional(
                    transcription_root, evidence_page.get("native_text_path")
                )
                normalized = _read_optional(
                    transcription_root, evidence_page.get("normalized_text_path")
                )
                paddle = normalized if route in {"paddle", "native_plus_paddle"} else None
                layout = _read_json_optional(
                    transcription_root, source_page.get("native_layout_path")
                )
                ocr = _read_json_optional(
                    transcription_root, evidence_page.get("paddle_result_path")
                )
                response = response_map.get((key, page_number))
                if response is None:
                    raise CommandError(
                        f"no completed Luna response for {key}:{page_number}"
                    )
                pages.append(
                    {
                        "document_key": key,
                        "page_key": page_id,
                        "pdf_page_number": page_number,
                        "printed_page_label": source_page.get("printed_page_label"),
                        "extraction_route": route,
                        "status": "transcribed",
                        "native_text": native_text,
                        "native_layout_json": layout,
                        "native_text_sha256": evidence_page.get("native_text_sha256"),
                        "paddle_text": paddle,
                        "paddle_result_json": ocr,
                        "paddle_text_sha256": evidence_page.get("normalized_text_sha256")
                        if paddle is not None
                        else None,
                        "luna_transcript_json": {
                            "page_id": page_id,
                            "pdf_page": page_number,
                            "text_fa": text_fa,
                        },
                        "luna_transcript_text": text_fa,
                        "luna_transcript_sha256": _hash_text(text_fa),
                        "luna_response_uri": response[0],
                        "luna_response_sha256": response[1],
                        "metadata": {
                            "package_path": source_page.get("package_path"),
                            "package_sha256": source_page.get("package_sha256"),
                            "response_path": response[2],
                        },
                    }
                )
        expected_pages = sum(int(d["page_count"]) for d in documents)
        if len(pages) != expected_pages:
            raise CommandError(
                f"page count mismatch: imported {len(pages)}, expected {expected_pages}"
            )
        if options["dry_run"]:
            self.stdout.write(
                f"validated {len(documents)} documents and {len(pages)} pages"
            )
            return ""

        with transaction.atomic():
            for row in documents:
                existing = PdfDocument.objects.filter(
                    document_key=row["document_key"]
                ).first()
                if existing is not None and existing.source_sha256 != row["source_sha256"]:
                    raise CommandError(
                        f"immutable document hash changed: {row['document_key']}"
                    )
                PdfDocument.objects.update_or_create(
                    document_key=row["document_key"],
                    defaults={
                        key: value for key, value in row.items() if key != "document_key"
                    },
                )
            for row in pages:
                document = PdfDocument.objects.get(document_key=row["document_key"])
                PdfPage.objects.update_or_create(
                    page_key=row["page_key"],
                    defaults={
                        key: value
                        for key, value in row.items()
                        if key not in {"page_key", "document_key"}
                    }
                    | {"document": document},
                )
        self.stdout.write(f"imported {len(documents)} documents and {len(pages)} pages")
        return ""
