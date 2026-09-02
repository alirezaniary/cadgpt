"""Load and validate the curated INBR catalog."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import cast

from cadgpt_regulations.errors import CatalogError, ManifestError
from cadgpt_regulations.jsonio import JsonObject, load_object, validate_schema
from cadgpt_regulations.resources import load_packaged_json
from cadgpt_regulations.urlpolicy import canonical_origin, validate_acquisition_url

CATALOG_SCHEMA_VERSION = "2.0.0"
DEFAULT_CATALOG_ID = "inbr-national-building-regulations"


def _catalog_schema() -> JsonObject:
    return load_packaged_json("cadgpt_regulations.schemas", "catalog.schema.json")


def _default_catalog() -> JsonObject:
    return load_packaged_json("cadgpt_regulations.data", "inbr_catalog.json")


def load_catalog(path: Path | None = None) -> JsonObject:
    """Load the default catalog or a schema-compatible catalog supplied by a caller."""
    try:
        data = (
            _default_catalog() if path is None else load_object(path, description="catalog")
        )
        validate_catalog(data)
    except ManifestError as exc:
        raise CatalogError(str(exc)) from exc
    return data


def validate_catalog(data: JsonObject) -> None:
    """Validate a catalog supplied in memory before it can drive an inventory."""
    try:
        validate_schema(data, _catalog_schema(), description="catalog")
        _validate_catalog_invariants(data)
    except ManifestError as exc:
        raise CatalogError(str(exc)) from exc


def _validate_catalog_invariants(catalog: JsonObject) -> None:
    families = cast(list[JsonObject], catalog["families"])
    artifacts = cast(list[JsonObject], catalog["artifacts"])
    metadata_sources = cast(list[JsonObject], catalog["metadata_sources"])
    policy = cast(JsonObject, catalog["acquisition_policy"])

    configured_origins = cast(list[str], policy["allowed_origins"])
    canonical_origins = [canonical_origin(origin) for origin in configured_origins]
    if canonical_origins != configured_origins:
        raise ManifestError("catalog acquisition origins must be canonical origins")
    if len(set(canonical_origins)) != len(canonical_origins):
        raise ManifestError("catalog acquisition origins must be unique")
    allowed_origins = frozenset(canonical_origins)

    family_keys = [cast(str, family["catalog_key"]) for family in families]
    artifact_keys = [cast(str, artifact["catalog_key"]) for artifact in artifacts]
    local_paths = [cast(str, artifact["local_path"]) for artifact in artifacts]
    artifact_orders = [cast(int, artifact["catalog_order"]) for artifact in artifacts]

    if len(set(family_keys)) != len(family_keys):
        raise ManifestError("catalog family keys must be unique")
    if len(set(artifact_keys)) != len(artifact_keys):
        raise ManifestError("catalog artifact keys must be unique")
    overlap = set(family_keys) & set(artifact_keys)
    if overlap:
        raise ManifestError(
            f"catalog family and artifact keys overlap: {sorted(overlap)!r}"
        )
    if len(set(local_paths)) != len(local_paths):
        raise ManifestError("catalog artifact local paths must be unique")
    if len(set(artifact_orders)) != len(artifact_orders):
        raise ManifestError("catalog artifact order values must be unique")
    if artifact_orders != sorted(artifact_orders):
        raise ManifestError("catalog artifacts must be stored in catalog order")
    for artifact in artifacts:
        local_path = cast(str, artifact["local_path"])
        remote_filename = cast(str, artifact["remote_filename"])
        if not _is_safe_flat_local_path(local_path):
            raise ManifestError(
                f"catalog local path must be a safe flat name: {local_path!r}"
            )
        if "\x00" in remote_filename:
            raise ManifestError("catalog remote filenames cannot contain NUL bytes")
        validate_acquisition_url(cast(str, artifact["download_url"]), allowed_origins)

    source_keys = [
        cast(str, metadata_source["source_key"]) for metadata_source in metadata_sources
    ]
    source_orders = [
        cast(int, metadata_source["catalog_order"]) for metadata_source in metadata_sources
    ]
    if len(set(source_keys)) != len(source_keys):
        raise ManifestError("catalog metadata source keys must be unique")
    if len(set(source_orders)) != len(source_orders):
        raise ManifestError("catalog metadata source order values must be unique")
    if source_orders != sorted(source_orders):
        raise ManifestError("catalog metadata sources must be stored in catalog order")
    for metadata_source in metadata_sources:
        requested_url = cast(str, metadata_source["requested_url"])
        validate_acquisition_url(requested_url, allowed_origins)
        expected_suffix = f"/{metadata_source['kind']}s/{metadata_source['wordpress_id']}"
        if not requested_url.endswith(expected_suffix):
            raise ManifestError(
                f"metadata source {metadata_source['source_key']} does not match its "
                "WordPress identity"
            )

    volumes = [cast(int, family["volume"]) for family in families]
    family_orders = [cast(int, family["catalog_order"]) for family in families]
    if volumes != list(range(1, 25)) or family_orders != list(range(1, 25)):
        raise ManifestError("catalog families must contain volumes 1 through 24 in order")

    all_keys = set(family_keys) | set(artifact_keys)
    for artifact in artifacts:
        relationships = cast(list[JsonObject], artifact["relationships"])
        relation_identities: set[tuple[str, str, int | None]] = set()
        for relationship in relationships:
            target = cast(str, relationship["target"])
            source_key = cast(str, artifact["catalog_key"])
            if target not in all_keys:
                raise ManifestError(
                    f"catalog relationship from {artifact['catalog_key']} has "
                    f"unknown target {target}"
                )
            if target == source_key:
                raise ManifestError(
                    f"catalog relationship on {source_key} cannot target itself"
                )
            identity = (
                cast(str, relationship["type"]),
                target,
                cast(int | None, relationship["order"]),
            )
            if identity in relation_identities:
                raise ManifestError(f"catalog relationship on {source_key} is duplicated")
            relation_identities.add(identity)
            if relationship["type"] == "APPENDIX_OF" and relationship["order"] is None:
                raise ManifestError(
                    f"APPENDIX_OF relationship on {source_key} needs an order"
                )
            if relationship["type"] != "APPENDIX_OF" and relationship["order"] is not None:
                raise ManifestError(
                    f"only APPENDIX_OF relationships may carry an order ({source_key})"
                )

        review_status = cast(str, artifact["review_status"])
        review_flags = cast(list[str], artifact["review_flags"])
        if review_status == "accepted" and review_flags:
            key = artifact["catalog_key"]
            raise ManifestError(
                f"accepted catalog artifact {key} cannot carry review flags"
            )
        if review_status == "needs_review" and not review_flags:
            raise ManifestError(
                f"catalog artifact {artifact['catalog_key']} needs a review flag"
            )
        if artifact["document_kind"] == "numbered_volume" and (
            artifact["legal_status"] != "binding_regulation"
        ):
            raise ManifestError(
                f"numbered volume {artifact['catalog_key']} must be a binding regulation"
            )
        if artifact["document_kind"] == "numbered_volume":
            volume = cast(int, artifact["volume"])
            edition_relations = [
                relationship
                for relationship in relationships
                if relationship["type"] == "EDITION_OF"
            ]
            expected_family = f"volume-{volume:02d}"
            if (
                len(edition_relations) != 1
                or edition_relations[0]["target"] != expected_family
            ):
                raise ManifestError(
                    f"numbered volume {artifact['catalog_key']} must be an edition of "
                    f"{expected_family}"
                )
        if artifact["document_kind"] in {"guide", "handbook"} and artifact[
            "legal_status"
        ] in {"binding_regulation", "binding_appendix"}:
            key = artifact["catalog_key"]
            raise ManifestError(
                f"supplementary guide {key} cannot be classified as binding"
            )

    appendices = [
        artifact
        for artifact in artifacts
        if any(
            relationship["type"] == "APPENDIX_OF"
            and relationship["target"] == "volume-19-edition-1404"
            for relationship in cast(list[JsonObject], artifact["relationships"])
        )
    ]
    appendix_orders = sorted(
        cast(int, relationship["order"])
        for artifact in appendices
        for relationship in cast(list[JsonObject], artifact["relationships"])
        if relationship["type"] == "APPENDIX_OF"
        and relationship["target"] == "volume-19-edition-1404"
    )
    if len(appendices) != 9 or appendix_orders != list(range(1, 10)):
        raise ManifestError("Volume 19 must have ordered appendices 1 through 9")
    for appendix in appendices:
        parent_links = [
            relationship
            for relationship in cast(list[JsonObject], appendix["relationships"])
            if relationship["type"] == "APPENDIX_OF"
            and relationship["target"] == "volume-19-edition-1404"
        ]
        if len(parent_links) != 1:
            key = appendix["catalog_key"]
            raise ManifestError(f"Volume 19 appendix {key} needs one ordered parent link")

    numbered_volumes = sorted(
        cast(int, artifact["volume"])
        for artifact in artifacts
        if artifact["document_kind"] == "numbered_volume"
    )
    if numbered_volumes != list(range(1, 25)):
        raise ManifestError(
            "catalog must contain one numbered artifact for each volume 1-24"
        )

    _require_relationship(
        artifacts,
        source="volume-04-protective-security-appendix-1403",
        relation_type="MANDATORY_APPENDIX_OF",
        target="volume-04-edition-1396",
    )
    for relation_source, relation_type, target in (
        ("volume-07-borehole-amendment-1405", "AMENDS", "volume-07-edition-1400"),
        ("volume-11-amendment-1403-08-08", "AMENDS", "volume-11-edition-1400"),
        (
            "volume-12-supervisor-clarification-1404",
            "CLARIFIES",
            "volume-12-edition-1392",
        ),
        ("volume-17-amendment-01", "AMENDS", "volume-17-edition-1403"),
    ):
        _require_relationship(
            artifacts,
            source=relation_source,
            relation_type=relation_type,
            target=target,
        )

    _require_relationship(
        artifacts,
        source="guide-masonry-perimeter-walls-v3-1404",
        relation_type="SUPERSEDES",
        target="guide-masonry-perimeter-walls-v2-1403",
    )


def _is_safe_flat_local_path(value: str) -> bool:
    if not value or value in {".", ".."} or "\x00" in value:
        return False
    if "/" in value or "\\" in value or Path(value).is_absolute():
        return False
    return not PureWindowsPath(value).drive


def _require_relationship(
    artifacts: list[JsonObject], *, source: str, relation_type: str, target: str
) -> None:
    matching = [artifact for artifact in artifacts if artifact["catalog_key"] == source]
    if len(matching) != 1:
        raise ManifestError(f"required catalog artifact is absent: {source}")
    relationships = cast(list[JsonObject], matching[0]["relationships"])
    if not any(
        relationship["type"] == relation_type and relationship["target"] == target
        for relationship in relationships
    ):
        raise ManifestError(f"{source} must {relation_type} {target}")
