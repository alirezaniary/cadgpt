"""Schema, coverage, and fail-closed publication checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from cadgpt_regulations.catalog import load_catalog, validate_catalog
from cadgpt_regulations.errors import ManifestError
from cadgpt_regulations.jsonio import JsonObject, sha256_json, validate_schema
from cadgpt_regulations.resources import load_packaged_json


@dataclass(frozen=True)
class PublishBlocker:
    local_path: str
    code: str
    diagnostic: str


def validate_manifest(manifest: JsonObject, *, catalog: JsonObject | None = None) -> None:
    """Validate schema plus counts and relationship integrity."""
    schema = load_packaged_json("cadgpt_regulations.schemas", "manifest.schema.json")
    validate_schema(manifest, schema, description="manifest")
    curated = load_catalog() if catalog is None else catalog
    validate_catalog(curated)
    catalog_metadata = cast(JsonObject, manifest["catalog"])
    if catalog_metadata["catalog_id"] != curated["catalog_id"]:
        raise ManifestError("manifest catalog id does not match the curated catalog")
    if catalog_metadata["schema_version"] != curated["schema_version"]:
        raise ManifestError("manifest catalog schema version does not match")
    if catalog_metadata["sha256"] != sha256_json(curated):
        raise ManifestError("manifest catalog digest does not match the curated catalog")
    if catalog_metadata["provenance"] != curated["provenance"]:
        raise ManifestError(
            "manifest catalog provenance does not match the curated catalog"
        )

    artifacts = cast(list[JsonObject], manifest["artifacts"])
    local_paths = [cast(str, artifact["local_path"]) for artifact in artifacts]
    if len(local_paths) != len(set(local_paths)):
        raise ManifestError("manifest artifact local paths must be unique")

    catalog_orders = [cast(int, artifact["catalog_order"]) for artifact in artifacts]
    if len(catalog_orders) != len(set(catalog_orders)):
        raise ManifestError("manifest catalog order values must be unique")
    if catalog_orders != sorted(catalog_orders):
        raise ManifestError("manifest artifacts must be stored in catalog order")

    artifact_keys = [
        cast(str, artifact["catalog_key"])
        for artifact in artifacts
        if artifact["catalog_key"] is not None
    ]
    if len(artifact_keys) != len(set(artifact_keys)):
        raise ManifestError("manifest catalog keys must be unique")

    expected_artifacts = cast(list[JsonObject], curated["artifacts"])
    expected_by_key = {
        cast(str, artifact["catalog_key"]): artifact for artifact in expected_artifacts
    }
    if set(artifact_keys) != set(expected_by_key):
        missing = sorted(set(expected_by_key) - set(artifact_keys))
        extra = sorted(set(artifact_keys) - set(expected_by_key))
        raise ManifestError(
            f"manifest catalog coverage differs; missing={missing!r}, extra={extra!r}"
        )

    copied_fields = (
        "catalog_order",
        "download_url",
        "remote_filename",
        "local_path",
        "expected_media_type",
        "expected_sha256",
        "expected_bytes",
        "expected_pdf_pages",
        "document_kind",
        "volume",
        "title_fa",
        "title_en",
        "translation_provenance",
        "edition",
        "legal_status",
        "relationships",
        "source_urls",
        "evidence",
        "review_status",
        "review_flags",
    )
    family_keys = {
        cast(str, family["catalog_key"])
        for family in cast(list[JsonObject], curated["families"])
    }
    keys = set(artifact_keys)
    for artifact in artifacts:
        key_value = artifact["catalog_key"]
        if key_value is not None:
            expected = expected_by_key[cast(str, key_value)]
            for field in copied_fields:
                if artifact[field] != expected[field]:
                    raise ManifestError(
                        f"manifest metadata for {key_value} differs at {field}"
                    )
        elif artifact["artifact_state"] == "ready":
            raise ManifestError(
                f"unaccounted artifact {artifact['local_path']} cannot be ready"
            )
        _validate_artifact_state(artifact)

        relation_identities: set[tuple[str, str, int | None]] = set()
        for relationship in cast(list[JsonObject], artifact["relationships"]):
            target = cast(str, relationship["target"])
            if target not in keys | family_keys:
                raise ManifestError(
                    f"relationship from {artifact['local_path']} has "
                    f"unknown artifact target {target}"
                )
            if target == key_value:
                raise ManifestError(
                    f"relationship from {artifact['local_path']} targets itself"
                )
            identity = (
                cast(str, relationship["type"]),
                target,
                cast(int | None, relationship["order"]),
            )
            if identity in relation_identities:
                raise ManifestError(
                    f"relationship from {artifact['local_path']} is duplicated"
                )
            relation_identities.add(identity)

    expected_summary = _recalculate_summary(artifacts)
    summary = cast(JsonObject, manifest["summary"])
    for field, expected_value in expected_summary.items():
        if summary[field] != expected_value:
            actual_value = summary[field]
            raise ManifestError(
                f"manifest summary {field} is {actual_value!r}, expected {expected_value!r}"
            )


def check_publishable(
    manifest: JsonObject, *, catalog: JsonObject | None = None
) -> tuple[PublishBlocker, ...]:
    """Return every reason the inventory cannot enter a published corpus."""
    validate_manifest(manifest, catalog=catalog)
    blockers: list[PublishBlocker] = []
    for artifact in cast(list[JsonObject], manifest["artifacts"]):
        local_path = cast(str, artifact["local_path"])
        state = cast(str, artifact["artifact_state"])
        error = cast(JsonObject | None, artifact["error"])
        if state != "ready":
            blockers.append(
                PublishBlocker(
                    local_path=local_path,
                    code=cast(str, error["code"])
                    if error is not None
                    else "NONTERMINAL_STATE",
                    diagnostic=(
                        cast(str, error["diagnostic"])
                        if error is not None
                        else f"artifact state is {state}"
                    ),
                )
            )
        if artifact["review_status"] == "needs_review":
            flags = cast(list[str], artifact["review_flags"])
            blockers.append(
                PublishBlocker(
                    local_path=local_path,
                    code="NEEDS_REVIEW",
                    diagnostic=", ".join(flags) or "catalog metadata needs review",
                )
            )
    return tuple(blockers)


def _recalculate_summary(artifacts: list[JsonObject]) -> JsonObject:
    actual = [artifact for artifact in artifacts if artifact["present"]]
    matched = [
        artifact
        for artifact in actual
        if artifact["catalog_key"] is not None
        and _error_code(artifact) != "EXPECTED_ARTIFACT_MISSING"
    ]
    ready_pdfs = [
        artifact
        for artifact in artifacts
        if artifact["artifact_state"] == "ready"
        and artifact["detected_media_type"] == "application/pdf"
    ]
    return {
        "expected_artifacts": sum(
            artifact["catalog_key"] is not None for artifact in artifacts
        ),
        "files_discovered": len(actual),
        "artifacts_accounted": len(matched),
        "valid_pdfs": len(ready_pdfs),
        "quarantined": sum(
            artifact["artifact_state"] == "quarantined" for artifact in artifacts
        ),
        "missing": sum(
            _error_code(artifact) == "EXPECTED_ARTIFACT_MISSING" for artifact in artifacts
        ),
        "unaccounted": sum(
            _error_code(artifact) == "UNACCOUNTED_ARTIFACT" for artifact in artifacts
        ),
        "needs_review": sum(
            artifact["review_status"] == "needs_review" for artifact in artifacts
        ),
        "pdf_pages": sum(cast(int, artifact["pdf_page_count"]) for artifact in ready_pdfs),
        "bytes": sum(cast(int, artifact["bytes"]) for artifact in ready_pdfs),
    }


def _error_code(artifact: JsonObject) -> str | None:
    error = cast(JsonObject | None, artifact["error"])
    return None if error is None else cast(str, error["code"])


def _validate_artifact_state(artifact: JsonObject) -> None:
    local_path = cast(str, artifact["local_path"])
    state = cast(str, artifact["artifact_state"])
    error = cast(JsonObject | None, artifact["error"])
    present = cast(bool, artifact["present"])
    media_type = cast(str | None, artifact["detected_media_type"])
    page_count = cast(int | None, artifact["pdf_page_count"])
    digest = cast(str | None, artifact["sha256"])
    expected_digest = cast(str | None, artifact["expected_sha256"])
    byte_size = cast(int | None, artifact["bytes"])
    expected_bytes = cast(int | None, artifact["expected_bytes"])
    expected_pages = cast(int | None, artifact["expected_pdf_pages"])

    if state == "ready":
        if error is not None:
            raise ManifestError(f"ready artifact {local_path} cannot carry an error")
        if not present or media_type != "application/pdf":
            raise ManifestError(f"ready artifact {local_path} must be a present PDF")
        if page_count is None or digest is None or byte_size is None:
            raise ManifestError(
                f"ready artifact {local_path} needs hash, size, and authoritative "
                "page count"
            )
        if expected_digest is None or digest != expected_digest:
            raise ManifestError(
                f"ready artifact {local_path} does not match its approved source bytes"
            )
        if expected_bytes is None or byte_size != expected_bytes:
            raise ManifestError(
                f"ready artifact {local_path} does not match its approved byte count"
            )
        if expected_pages is None or page_count != expected_pages:
            raise ManifestError(
                f"ready artifact {local_path} does not match its approved page count"
            )
    elif state == "quarantined" and error is None:
        raise ManifestError(f"quarantined artifact {local_path} must carry an error")
    elif state == "pending" and error is not None:
        raise ManifestError(f"pending artifact {local_path} cannot carry a terminal error")

    if not present:
        if _error_code(artifact) != "EXPECTED_ARTIFACT_MISSING":
            raise ManifestError(
                f"absent artifact {local_path} needs EXPECTED_ARTIFACT_MISSING"
            )
        if any(value is not None for value in (media_type, page_count, digest, byte_size)):
            raise ManifestError(f"absent artifact {local_path} cannot carry file metadata")
    if media_type != "application/pdf" and page_count is not None:
        raise ManifestError(f"non-PDF artifact {local_path} cannot carry a PDF page count")
    if (
        present
        and digest is not None
        and expected_digest is not None
        and digest != expected_digest
        and (state != "quarantined" or _error_code(artifact) != "SOURCE_HASH_MISMATCH")
    ):
        raise ManifestError(
            f"artifact {local_path} with unapproved source bytes must be quarantined"
        )

    review_status = cast(str, artifact["review_status"])
    review_flags = cast(list[str], artifact["review_flags"])
    if review_status == "accepted" and review_flags:
        raise ManifestError(f"accepted artifact {local_path} cannot carry review flags")
    if review_status == "needs_review" and not review_flags:
        raise ManifestError(f"artifact {local_path} needs at least one review flag")
