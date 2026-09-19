#!/usr/bin/env python3
"""Choose one authoritative rule-extraction draft per INBR chunk, and say why.

``.cadgpt/inbr/worker-drafts/`` holds many independent worker runs against the same 668
chunks (see ``docs/tasks/T-0106-authoritative-draft-per-chunk.md``). Nothing upstream of
this tool says which draft file is authoritative when more than one exists for a chunk,
and a prior ad-hoc import picked whichever file a loop happened to see first -- verified
2026-09-19 to have pulled two thirds of its rule candidates from the templated stub
sources (``rule-worker-a/b/c``'s original run). This tool replaces "whatever the loop saw
first" with one deterministic, written-down rule, applied the same way every time.

This tool only reads ``worker-drafts/`` and the extraction ledger. It never writes to
either. Its own output -- the index -- is data, written to a caller-supplied path.

Selection rule
---------------
Every file under ``worker-drafts/`` (excluding ``previews/``) whose name matches
``chunk-<N>-extraction.json`` -- as a suffix, so ``repair-chunk-42-extraction.json`` and
``volume-09-chunk-166-extraction.json`` both count, for chunk 42 and chunk 166
respectively -- is a *candidate* for chunk ``N``. Candidates for a chunk are filtered in
this order; the first stage that rejects a candidate is the recorded reason, and a chunk
whose candidates are all rejected is ``unresolved``:

1. ``parse_error`` -- the file fails to parse. Operationalised as: invalid JSON; OR fails
   validation against
   ``packages/regulations/src/cadgpt_regulations/schemas/provisional-extraction.schema.json``
   (reused, not reimplemented -- see ``cadgpt_regulations.jsonio``); OR its ``items``
   array, though schema-valid, is empty. An extraction with zero items analysed nothing
   and cannot be authoritative for a chunk whose transcript has content.
2. ``templated`` -- every item carries a ``reason`` (outcome ``no_assertion``) or
   ``rule.unsupported_reason`` (outcome ``candidate``) value, and those values collapse to
   at most one distinct string across the whole file (more than one item required). This
   is deliberately *not* literal matching against the three known hardcoded Persian
   sentences from ``docs/inbr-haiku-remediation-runbook.md``'s verification script: that
   approach was tried first and missed a fourth stub variant (``rule-worker-c``, 1,393
   items, one sentence differing from a known one only in its last two words) --
   literal matching can never be complete against an unknown number of template variants.
   Detecting the actual signature (every record gets the identical canned sentence,
   regardless of its exact wording) instead of specific wordings is what makes this stage
   catch stub sources this tool has not seen before. See ``_collapse_check`` for the exact
   rule. A file with even one item outside the collapsed set survives this stage.
3. ``record_id_mismatch`` -- the file's ``items[*].record_id`` set does not exactly equal
   the chunk's transcript ``sections[*].record_id`` set. The transcript is resolved via
   ``ledger.json``'s ``jobs[N-1].structured_transcript_path`` (``chunk_order`` is
   1-indexed and matches array position -- verified across all 668 jobs before relying on
   it). This stage catches partial, merged, or wrongly-numbered extractions that the first
   two stages would not.
4. Among survivors, prefer the newest by directory generation. This is operationalised as
   the candidate file's own filesystem ``mtime``: empirically, on this checkout, every
   file a single worker run dropped carries mtimes within one narrow window (minutes), so
   mtime recovers the generation ordering directly -- ``haiku-pass-1`` (2026-09-18) is
   unambiguously newest against every ``rule-worker-*``/``luna-*`` directory populated
   2026-09-14 through 2026-09-16 -- without a hand-maintained directory-name table that
   would silently go stale the next time a worker batch is added. If two survivors tie on
   mtime, the lexicographically smaller path wins, so the result is stable for a fixed,
   unmodified tree. Every survivor that is not chosen is recorded with reason
   ``superseded`` and the path of the file that won.

This mtime-based rule is a deliberate deviation from the task's literal suggestion of a
hand-maintained directory-generation table: worker directory names in this corpus
(``rule-worker-1``, ``luna-resume-14``, ``luna-rule-resume-31``, ...) do not encode
generation order themselves, so a table would have to be derived from the same evidence
(timestamps) this rule reads directly, and would need updating by hand for every future
worker batch. Determinism is preserved because the proof this tool must satisfy --
"run it twice into two paths and show equal SHA-256 sums" -- concerns one unmodified
checkout, across which file mtimes do not change between the two runs.

Index format
------------
See ``build_index`` for the exact structure. In short: a ``summary`` with resolved/
unresolved/rejection counts, a ``chunks`` array (one entry per resolved chunk, with the
chosen file, its SHA-256, and every rejected candidate's reason), and an ``unresolved``
array (one entry per chunk with zero surviving candidates, itself carrying every
candidate's rejection reason so nothing is silently dropped).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from cadgpt_regulations.errors import ManifestError
from cadgpt_regulations.jsonio import loads_object, validate_schema

# This file is itself a terminal-facing CLI; its output is deliberate.
# ruff: noqa: T201

Json = dict[str, Any]

_CANDIDATE_NAME = re.compile(r"chunk-0*(\d+)-extraction\.json$")
_CHUNK_COUNT = 668

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages/regulations/src/cadgpt_regulations"
    / "schemas/provisional-extraction.schema.json"
)


def discover_candidates(worker_drafts: Path) -> dict[int, list[Path]]:
    """Group every candidate file under ``worker_drafts`` by chunk number.

    Skips any directory literally named ``previews`` at any depth. Traversal order is
    sorted at every level so the result -- and everything downstream of it -- does not
    depend on the operating system's directory-entry order.
    """
    by_chunk: dict[int, list[Path]] = {}
    for root, dirs, files in os.walk(worker_drafts):
        dirs.sort()
        if Path(root).name == "previews":
            dirs[:] = []
            continue
        for name in sorted(files):
            match = _CANDIDATE_NAME.search(name)
            if match is None:
                continue
            chunk = int(match.group(1))
            by_chunk.setdefault(chunk, []).append(Path(root) / name)
    for paths in by_chunk.values():
        paths.sort()
    return by_chunk


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _collapse_check(items: list[Json]) -> tuple[bool, int, int]:
    """Detect a templated (scripted-stub) file by reason-text diversity, not literal text.

    A first version of this tool matched three known hardcoded Persian sentences
    literally. That missed a fourth stub variant used by ``rule-worker-c`` (verified: all
    1,393 of its items share one ``reason`` string differing from the three known
    sentences only in its last two words -- ``بازبینی معنایی`` vs ``بازبینی منبع`` -- a
    template with the wrong word substituted in once, not three different templates).
    Literal matching can never be complete against an unknown number of template variants,
    so this checks the actual signature a scripted stub produces regardless of its exact
    wording: every record gets the *same* canned sentence, so the file's population of
    ``reason`` (outcome ``no_assertion``) / ``rule.unsupported_reason`` (outcome
    ``candidate``) values collapses to at most one distinct string. Genuine analysis -- by
    a human or a model actually reading each record -- produces a different sentence per
    record; a script stamping one string does not.

    Returns ``(is_templated, distinct_reason_count, items_with_reason)``. ``is_templated``
    requires every item to carry a reason/unsupported_reason value (a file mixing real
    structured rules that carry neither field with a few templated ones does not collapse)
    and at most one distinct value among them, with more than one item total (a single-item
    file cannot show repetition).
    """
    values: list[str] = []
    for item in items:
        outcome = item.get("outcome")
        value: Any = None
        if outcome == "candidate":
            rule = item.get("rule")
            value = rule.get("unsupported_reason") if isinstance(rule, dict) else None
        elif outcome == "no_assertion":
            value = item.get("reason")
        if isinstance(value, str) and value:
            values.append(value)
    distinct = len(set(values))
    is_templated = len(items) > 1 and len(values) == len(items) and distinct <= 1
    return is_templated, distinct, len(values)


def _load_candidate(path: Path, schema: Json) -> tuple[Json | None, str | None]:
    """Parse and schema-validate one candidate file.

    Returns ``(document, None)`` on success or ``(None, detail)`` naming the parse_error.
    An empty ``items`` array is treated as a parse failure: it is schema-valid but
    analysed nothing, so it can never be authoritative for a non-empty transcript.
    """
    try:
        document = loads_object(path.read_text(encoding="utf-8"), description=str(path))
        validate_schema(document, schema, description=str(path))
    except ManifestError as exc:
        return None, str(exc)
    items = document.get("items")
    if not isinstance(items, list) or not items:
        return None, "items array is empty; the extraction analysed nothing"
    return document, None


def load_ledger_jobs(ledger_path: Path) -> list[Json]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    jobs = ledger["jobs"]
    if len(jobs) != _CHUNK_COUNT:
        raise ValueError(f"ledger has {len(jobs)} jobs, expected {_CHUNK_COUNT}")
    for index, job in enumerate(jobs):
        if job["chunk_order"] != index + 1:
            raise ValueError(
                f"ledger job at index {index} has chunk_order {job['chunk_order']!r}, "
                f"expected {index + 1} (jobs[N-1].chunk_order must equal N)"
            )
    return jobs


def _transcript_record_ids(
    ledger_dir: Path, job: Json
) -> tuple[str | None, set[str] | None, str | None]:
    """Resolve one chunk's transcript and return (raw_path, record_ids, error)."""
    raw_path = job.get("structured_transcript_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None, None, "ledger job has no structured_transcript_path"
    transcript_path = (ledger_dir / raw_path).resolve()
    try:
        transcript_path.relative_to(ledger_dir.resolve())
    except ValueError:
        detail = f"structured_transcript_path escapes ledger directory: {raw_path}"
        return raw_path, None, detail
    try:
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        sections = transcript["sections"]
        record_ids = {section["record_id"] for section in sections}
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return raw_path, None, f"cannot read transcript {transcript_path}: {exc}"
    return raw_path, record_ids, None


def _record_id_mismatch_detail(item_ids: set[str], transcript_ids: set[str]) -> str:
    missing = sorted(transcript_ids - item_ids)
    extra = sorted(item_ids - transcript_ids)
    return (
        f"record_id sets differ: {len(missing)} in transcript but not items "
        f"(e.g. {missing[:5]}), {len(extra)} in items but not transcript (e.g. {extra[:5]})"
    )


def evaluate_chunk(
    chunk: int,
    candidates: list[Path],
    schema: Json,
    raw_transcript_path: str | None,
    transcript_record_ids: set[str] | None,
    transcript_error: str | None,
) -> Json:
    """Apply the selection rule to one chunk's candidates and return its index entry."""
    rejected: list[Json] = []
    survivors: list[tuple[Path, Json, int, int, int]] = []

    for path in candidates:
        rel = str(path)
        document, parse_detail = _load_candidate(path, schema)
        if document is None:
            rejected.append({"path": rel, "reason": "parse_error", "detail": parse_detail})
            continue
        items = document["items"]
        is_templated, distinct_reasons, items_with_reason = _collapse_check(items)
        if is_templated:
            rejected.append(
                {
                    "path": rel,
                    "reason": "templated",
                    "detail": (
                        f"{items_with_reason}/{len(items)} items carry a "
                        f"reason/unsupported_reason and collapse to {distinct_reasons} "
                        "distinct string"
                    ),
                }
            )
            continue
        if transcript_record_ids is None:
            rejected.append(
                {
                    "path": rel,
                    "reason": "record_id_mismatch",
                    "detail": f"transcript unavailable: {transcript_error}",
                }
            )
            continue
        item_ids = {item["record_id"] for item in items}
        if item_ids != transcript_record_ids:
            rejected.append(
                {
                    "path": rel,
                    "reason": "record_id_mismatch",
                    "detail": _record_id_mismatch_detail(item_ids, transcript_record_ids),
                }
            )
            continue
        survivors.append((path, document, distinct_reasons, items_with_reason, len(items)))

    if not survivors:
        return {
            "chunk": chunk,
            "structured_transcript_path": raw_transcript_path,
            "rejected": sorted(rejected, key=lambda r: (r["path"],)),
        }

    def sort_key(entry: tuple[Path, Json, int, int, int]) -> tuple[float, str]:
        path = entry[0]
        return (-path.stat().st_mtime, str(path))

    survivors.sort(key=sort_key)
    chosen = survivors[0]
    chosen_path, chosen_doc, chosen_distinct, chosen_with_reason, chosen_total = chosen
    for path, _doc, _dr, _wr, _to in survivors[1:]:
        rejected.append(
            {
                "path": str(path),
                "reason": "superseded",
                "detail": f"chosen file is newer or lexicographically prior: {chosen_path}",
            }
        )

    return {
        "chunk": chunk,
        "structured_transcript_path": raw_transcript_path,
        "chosen": {
            "path": str(chosen_path),
            "sha256": _sha256_file(chosen_path),
            "worker_id": chosen_doc.get("worker_id"),
            "mtime": chosen_path.stat().st_mtime,
            "collapse_check": {
                "total_items": chosen_total,
                "items_with_reason": chosen_with_reason,
                "distinct_reasons": chosen_distinct,
                "verdict": "not_templated",
            },
        },
        "rejected": sorted(rejected, key=lambda r: (r["path"],)),
    }


def build_index(worker_drafts: Path, ledger_path: Path) -> Json:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    candidates_by_chunk = discover_candidates(worker_drafts)
    jobs = load_ledger_jobs(ledger_path)
    ledger_dir = ledger_path.parent

    chunks: list[Json] = []
    unresolved: list[Json] = []
    files_considered = 0
    files_rejected_parse_error = 0
    files_rejected_templated = 0
    files_rejected_record_id_mismatch = 0
    files_rejected_superseded = 0
    chunks_with_multiple_candidates = 0

    for chunk in range(1, _CHUNK_COUNT + 1):
        candidates = candidates_by_chunk.get(chunk, [])
        files_considered += len(candidates)
        if len(candidates) > 1:
            chunks_with_multiple_candidates += 1
        raw_transcript_path, transcript_ids, transcript_error = _transcript_record_ids(
            ledger_dir, jobs[chunk - 1]
        )
        entry = evaluate_chunk(
            chunk, candidates, schema, raw_transcript_path, transcript_ids, transcript_error
        )
        for rejection in entry["rejected"]:
            reason = rejection["reason"]
            if reason == "parse_error":
                files_rejected_parse_error += 1
            elif reason == "templated":
                files_rejected_templated += 1
            elif reason == "record_id_mismatch":
                files_rejected_record_id_mismatch += 1
            elif reason == "superseded":
                files_rejected_superseded += 1
        if "chosen" in entry:
            chunks.append(
                {
                    "chunk": entry["chunk"],
                    "structured_transcript_path": entry["structured_transcript_path"],
                    "chosen": entry["chosen"],
                    "rejected": entry["rejected"],
                }
            )
        else:
            unresolved.append(
                {
                    "chunk": entry["chunk"],
                    "structured_transcript_path": entry["structured_transcript_path"],
                    "candidates": entry["rejected"],
                }
            )

    summary = {
        "chunks_total": _CHUNK_COUNT,
        "chunks_resolved": len(chunks),
        "chunks_unresolved": len(unresolved),
        "chunks_with_multiple_candidates": chunks_with_multiple_candidates,
        "files_considered": files_considered,
        "files_chosen": len(chunks),
        "files_rejected_parse_error": files_rejected_parse_error,
        "files_rejected_templated": files_rejected_templated,
        "files_rejected_record_id_mismatch": files_rejected_record_id_mismatch,
        "files_rejected_superseded": files_rejected_superseded,
    }
    assert summary["chunks_resolved"] + summary["chunks_unresolved"] == _CHUNK_COUNT

    return {
        "schema_version": "inbr-draft-index-1.0.0",
        "generated_from": {
            "worker_drafts": str(worker_drafts),
            "ledger": str(ledger_path),
            "extraction_schema": str(_SCHEMA_PATH),
        },
        "summary": summary,
        "chunks": chunks,
        "unresolved": unresolved,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker-drafts", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    index = build_index(args.worker_drafts, args.ledger)

    parent_existed = args.out.parent.exists()
    args.out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not parent_existed:
        # Only tighten permissions on a directory this run created itself -- mkdir's
        # `mode` argument is silently ignored by Python when the directory already
        # exists (exist_ok=True), and an unconditional chmod here would otherwise strip
        # permissions from a pre-existing, possibly shared directory the caller pointed
        # `--out` at (reproduced against a pre-existing 0755 directory before this fix).
        args.out.parent.chmod(0o700)
    payload = json.dumps(index, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    args.out.write_text(payload, encoding="utf-8")
    args.out.chmod(0o600)

    summary = index["summary"]
    print(
        f"chunks_resolved={summary['chunks_resolved']} "
        f"chunks_unresolved={summary['chunks_unresolved']} "
        f"(sum={summary['chunks_resolved'] + summary['chunks_unresolved']}, "
        f"expected {summary['chunks_total']})"
    )
    for entry in index["unresolved"]:
        print(f"unresolved chunk {entry['chunk']}: {entry['candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
