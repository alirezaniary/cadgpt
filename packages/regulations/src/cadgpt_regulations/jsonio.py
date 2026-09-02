"""Strict and deterministic JSON I/O."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from cadgpt_regulations.errors import ManifestError

type JsonObject = dict[str, Any]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def loads_object(text: str, *, description: str) -> JsonObject:
    """Decode one JSON object while rejecting duplicate keys."""
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ManifestError(f"{description} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"{description} must contain a JSON object")
    return cast(JsonObject, value)


def load_object(path: Path, *, description: str) -> JsonObject:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read {description} {path}: {exc}") from exc
    return loads_object(text, description=description)


def canonical_bytes(value: JsonObject) -> bytes:
    """Return the one serialization used for manifests and content identity."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode()


def sha256_json(value: JsonObject) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_schema(value: JsonObject, schema: JsonObject, *, description: str) -> None:
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    error = errors[0]
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    raise ManifestError(f"{description} schema error at {location}: {error.message}")
