#!/usr/bin/env python3
"""Create bounded display copies of existing renders, never new PDF renders."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image


def preview_bytes(payload: bytes) -> bytes:
    with Image.open(io.BytesIO(payload)) as source:
        image = source.convert("RGB")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        for quality in (85, 75, 65, 55):
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            result = output.getvalue()
            if len(result) <= 384 * 1024:
                return result
    raise ValueError("Preview exceeds display budget; inspect smaller detailed crops")


def install(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"Refusing to overwrite differing preview: {path}")
        return
    with path.open("xb") as stream:
        stream.write(payload)
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk", type=int, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    run = repo / ".cadgpt/inbr"
    evidence = (run / "transcription/revision-2026-09-09-paddle").resolve()
    queue = json.loads(
        (run / "extraction/revision-2026-09-09-paddle/jobs.json").read_text()
    )
    job = next(job for job in queue["jobs"] if job["chunk_order"] == args.chunk)
    dest = run / "worker-drafts/previews" / f"chunk-{args.chunk}-jpeg-v1"
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.chmod(0o700)
    pages = []
    for page in job["pages"]:
        relative = page.get("page_render_path")
        if relative is None:
            continue
        if page["route"] not in ("ocr", "native_plus_ocr"):
            raise ValueError("Refusing image processing for a non-OCR route")
        source = (evidence / relative).resolve()
        source.relative_to(evidence)
        payload = source.read_bytes()
        source_hash = hashlib.sha256(payload).hexdigest()
        if source_hash != page["page_render_sha256"]:
            raise ValueError(f"Source render hash mismatch: {source}")
        output = preview_bytes(payload)
        target = dest / f"page-{page['pdf_page']:06d}-{source_hash[:12]}.jpg"
        install(target, output)
        pages.append(
            {
                "page_id": page["page_id"],
                "pdf_page": page["pdf_page"],
                "source_render": str(source),
                "source_sha256": source_hash,
                "preview": str(target),
                "bytes": len(output),
                "preview_sha256": hashlib.sha256(output).hexdigest(),
            }
        )
    manifest = {
        "job_id": job["job_id"],
        "chunk_order": args.chunk,
        "purpose": "Display only; inspect detailed crops for unclear content",
        "pages": pages,
    }
    install(dest / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    sys.stdout.write(
        json.dumps(
            {
                "chunk": args.chunk,
                "manifest": str(dest / "manifest.json"),
                "images": len(pages),
                "total_bytes": sum(p["bytes"] for p in pages),
            }
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
