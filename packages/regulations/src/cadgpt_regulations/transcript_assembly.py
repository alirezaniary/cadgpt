"""Attest completed Luna chunks and assemble source books without filling gaps."""

from __future__ import annotations

from pathlib import Path

from cadgpt_regulations.jsonio import JsonObject, canonical_bytes, loads_object, sha256_json
from cadgpt_regulations.luna_transcript import (
    TRANSCRIPT_PASSES,
    LunaTranscriptError,
    _validate_response,
    validate_luna_jobs,
    validate_luna_ledger,
    validate_response_pages,
    validate_structured_transcript,
)
from cadgpt_regulations.storage import (
    ensure_private_tree,
    install_immutable_bytes,
    read_attested_bytes,
    safe_path,
)


def read_completed_chunk(job: JsonObject, record: JsonObject, root: Path) -> JsonObject:
    """Re-attest both outputs and the complete ordered page representation."""
    if record["status"] != "completed":
        raise LunaTranscriptError(f"chunk {job['chunk_order']} is not complete")
    values = {}
    for kind in ("response", "structured_transcript"):
        payload, _ = read_attested_bytes(
            safe_path(root, record[f"{kind}_path"]),
            expected_sha256=record[f"{kind}_sha256"],
        )
        values[kind] = loads_object(payload.decode("utf-8"), description=kind)
    response = values["response"]
    structured = values["structured_transcript"]
    _validate_response(response, job=job, pass_name=TRANSCRIPT_PASSES[0])
    validate_structured_transcript(structured, job=job)
    if response["structured_transcript"] != structured:
        raise LunaTranscriptError("response differs from stored structured transcript")
    validate_response_pages(response, job=job)
    return response


def audit_luna_transcripts(
    queue: JsonObject,
    ledger: JsonObject,
    acquisition: JsonObject,
    *,
    output_root: Path,
    acquisition_root: Path,
) -> tuple[JsonObject, list[JsonObject]]:
    """Audit a snapshot; incomplete books are returned in memory, never installed."""
    validate_luna_jobs(queue)
    validate_luna_ledger(ledger, queue=queue)
    artifacts = acquisition["artifacts"]
    if any(artifact["state"] != "ready" for artifact in artifacts):
        raise LunaTranscriptError("acquisition has unavailable source documents")
    sources = {artifact["catalog_key"]: artifact for artifact in artifacts}
    if len(sources) != len(artifacts):
        raise LunaTranscriptError("duplicate acquisition document")
    if set(sources) != {job["catalog_key"] for job in queue["jobs"]}:
        raise LunaTranscriptError("queue does not cover exactly the acquired documents")
    canonical_order = [
        (job["catalog_order"], job["start_pdf_page"], job["end_pdf_page"])
        for job in queue["jobs"]
    ]
    if canonical_order != sorted(canonical_order):
        raise LunaTranscriptError("queue documents are not in canonical page order")
    records = {record["job_id"]: record for record in ledger["jobs"]}
    books = {}
    for key, artifact in sources.items():
        read_attested_bytes(
            safe_path(acquisition_root, artifact["artifact_path"]),
            expected_sha256=artifact["sha256"],
            expected_bytes=artifact["bytes"],
        )
        books[key] = {
            "schema_version": "1.0.0",
            "boundary": "persian_structured_transcript",
            "source": {
                "catalog_key": key,
                "catalog_order": artifact["catalog_order"],
                "sha256": artifact["sha256"],
                "pdf_page_count": artifact["pdf_page_count"],
                "artifact_path": artifact["artifact_path"],
            },
            "pages": [],
            "chunks": [],
            "overlaps": [],
        }
    queued_pages: dict[str, list[int]] = {key: [] for key in sources}
    finished_pages: dict[str, dict[str, JsonObject]] = {key: {} for key in sources}
    completed = 0
    for job in queue["jobs"]:
        key = job["catalog_key"]
        artifact = sources[key]
        if (
            job["source_sha256"] != artifact["sha256"]
            or job["source_bytes"] != artifact["bytes"]
            or job["catalog_order"] != artifact["catalog_order"]
            or job["original_pdf"]
            != {
                "path": artifact["artifact_path"],
                "sha256": artifact["sha256"],
                "bytes": artifact["bytes"],
            }
        ):
            raise LunaTranscriptError("queue source identity differs from acquisition")
        declared_overlap = job.get("overlap_page_ids")
        if not isinstance(declared_overlap, list):
            raise LunaTranscriptError("job lacks an explicit overlap declaration")
        for page in job["pages"]:
            expected_id = f"sha256:{artifact['sha256']}:page:{page['pdf_page']:06d}"
            if page["page_id"] != expected_id:
                raise LunaTranscriptError("job page identity differs from its source PDF")
            if page["page_id"] not in declared_overlap:
                queued_pages[key].append(page["pdf_page"])
        record = records[job["job_id"]]
        if record["status"] != "completed":
            continue
        response = read_completed_chunk(job, record, output_root)
        book = books[key]
        book["chunks"].append(
            {
                "job_id": job["job_id"],
                "chunk_order": job["chunk_order"],
                "start_pdf_page": job["start_pdf_page"],
                "end_pdf_page": job["end_pdf_page"],
                "ordered_page_ids": response["ordered_page_ids"],
                "overlap_page_ids": declared_overlap,
                "response_path": record["response_path"],
                "response_sha256": record["response_sha256"],
                "structured_transcript_path": record["structured_transcript_path"],
                "structured_transcript_sha256": record["structured_transcript_sha256"],
                "structured_transcript": response["structured_transcript"],
            }
        )
        for page in response["page_transcripts"]:
            page_id = page["page_id"]
            if page_id in declared_overlap:
                # The earlier chunk owns this page; retain any later reading explicitly.
                earlier = finished_pages[key].get(page_id)
                book["overlaps"].append(
                    {
                        "page_id": page_id,
                        "chunk_order": job["chunk_order"],
                        "text_fa": page["text_fa"],
                        "agrees_with_owner": None
                        if earlier is None
                        else earlier["text_fa"] == page["text_fa"],
                    }
                )
                continue
            if page_id in finished_pages[key]:
                raise LunaTranscriptError("unexpected duplicate completed page")
            value = {**page, "chunk_order": job["chunk_order"]}
            finished_pages[key][page_id] = value
            book["pages"].append(value)
        completed += 1
    for key, artifact in sources.items():
        if queued_pages[key] != list(range(1, artifact["pdf_page_count"] + 1)):
            raise LunaTranscriptError(f"queue has missing or duplicated pages: {key}")
    ordered_books = sorted(books.values(), key=lambda book: book["source"]["catalog_order"])
    ready_books = 0
    for book in ordered_books:
        book["complete"] = [page["pdf_page"] for page in book["pages"]] == list(
            range(1, book["source"]["pdf_page_count"] + 1)
        )
        ready_books += book["complete"]
    report = {
        "schema_version": "1.0.0",
        "boundary": "persian_structured_transcript",
        "queue_sha256": sha256_json(queue),
        "ledger_sha256": sha256_json(ledger),
        "acquisition_sha256": sha256_json(acquisition),
        "complete": completed == len(queue["jobs"]) and ready_books == len(books),
        "summary": {
            "chunks_expected": len(queue["jobs"]),
            "chunks_completed": completed,
            "documents_expected": len(books),
            "documents_complete": ready_books,
            "pages_expected": sum(a["pdf_page_count"] for a in artifacts),
            "pages_completed": sum(len(book["pages"]) for book in ordered_books),
            "overlap_reading_disagreements": sum(
                overlap["agrees_with_owner"] is False
                for book in ordered_books
                for overlap in book["overlaps"]
            ),
        },
    }
    return report, ordered_books


def install_assembled_transcripts(
    report: JsonObject, books: list[JsonObject], *, output_root: Path
) -> Path:
    """Install only a fully audited cohort, with content-addressed book outputs."""
    if not report["complete"] or not all(book["complete"] for book in books):
        raise LunaTranscriptError("cannot assemble while any required chunk is incomplete")
    references = []
    for book in books:
        directory = ensure_private_tree(
            output_root, f"assembled/books/{book['source']['sha256']}"
        )
        digest = sha256_json(book)
        path = directory / f"{digest}.json"
        install_immutable_bytes(path, canonical_bytes(book), expected_sha256=digest)
        references.append(
            {
                "source": book["source"],
                "path": path.relative_to(output_root).as_posix(),
                "sha256": digest,
            }
        )
    manifest = {**report, "books": references}
    directory = ensure_private_tree(output_root, "assembled/manifests")
    digest = sha256_json(manifest)
    path = directory / f"{digest}.json"
    install_immutable_bytes(path, canonical_bytes(manifest), expected_sha256=digest)
    return path
