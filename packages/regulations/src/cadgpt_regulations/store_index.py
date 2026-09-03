"""Complete inventory validation for generated regulation evidence stores."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from cadgpt_regulations.errors import TranscriptionError
from cadgpt_regulations.jsonio import JsonObject, loads_object
from cadgpt_regulations.storage import (
    StorageError,
    read_attested_bytes,
    safe_path,
    snapshot_directory,
    validate_output_root,
)


def validate_output_inventory(root: Path) -> None:
    """Reject every generated file that is not reachable from an immutable index."""
    try:
        validate_output_root(root)
        snapshot = snapshot_directory(root)
        actual = {entry.path for entry in snapshot.entries if entry.kind == "file"}
        index_paths = sorted(path for path in actual if path.startswith("indexes/"))
        expected: set[str] = set(index_paths)
        for index_path in index_paths:
            payload, _ = read_attested_bytes(safe_path(root, index_path))
            index = loads_object(payload.decode("utf-8"), description="evidence index")
            kind_value = index.get("kind")
            kind = kind_value if isinstance(kind_value, str) else ""
            required = {
                "page_probe": {
                    "schema_version",
                    "kind",
                    "manifest_path",
                    "manifest_sha256",
                    "configuration_sha256",
                    "toolchain_sha256",
                },
                "transcription": {
                    "schema_version",
                    "kind",
                    "manifest_path",
                    "manifest_sha256",
                    "configuration_sha256",
                    "probe_sha256",
                },
                "transcription_check": {
                    "schema_version",
                    "kind",
                    "report_path",
                    "report_sha256",
                    "transcription_sha256",
                },
            }.get(kind)
            if (
                required is None
                or set(index) != required
                or index["schema_version"] != "1.0.0"
            ):
                raise TranscriptionError(
                    f"generated evidence index is invalid: {index_path}"
                )
            if kind == "transcription_check":
                report_path = cast(str, index["report_path"])
                read_attested_bytes(
                    safe_path(root, report_path),
                    expected_sha256=cast(str, index["report_sha256"]),
                )
                expected.add(report_path)
                continue
            manifest_path = cast(str, index["manifest_path"])
            manifest_payload, _ = read_attested_bytes(
                safe_path(root, manifest_path),
                expected_sha256=cast(str, index["manifest_sha256"]),
            )
            expected.add(manifest_path)
            manifest = loads_object(
                manifest_payload.decode("utf-8"), description="indexed manifest"
            )
            if kind == "page_probe":
                _index_probe_files(manifest, expected)
            else:
                _index_transcription_files(root, manifest, expected)
        actual_directories = {
            entry.path for entry in snapshot.entries if entry.kind == "directory"
        }
        expected_directories: set[str] = set()
        for value in expected:
            parent = Path(value).parent
            while parent != Path():
                expected_directories.add(parent.as_posix())
                parent = parent.parent
        if actual != expected or actual_directories != expected_directories:
            unindexed = sorted(actual - expected)
            missing = sorted(expected - actual)
            unindexed_directories = sorted(actual_directories - expected_directories)
            missing_directories = sorted(expected_directories - actual_directories)
            raise TranscriptionError(
                f"generated evidence inventory differs: unindexed={unindexed!r}, "
                f"missing={missing!r}, unindexed_directories={unindexed_directories!r}, "
                f"missing_directories={missing_directories!r}"
            )
    except StorageError as exc:
        raise TranscriptionError(str(exc)) from exc


def _index_probe_files(manifest: JsonObject, expected: set[str]) -> None:
    for document in cast(list[JsonObject], manifest.get("documents", [])):
        for page in cast(list[JsonObject], document.get("pages", [])):
            package = page.get("package_path")
            if isinstance(package, str):
                expected.update(
                    {
                        f"{package}/native.json",
                        f"{package}/page.json",
                        f"{package}/render.png",
                    }
                )


def _index_transcription_files(
    root: Path, manifest: JsonObject, expected: set[str]
) -> None:
    for document in cast(list[JsonObject], manifest.get("documents", [])):
        for page in cast(list[JsonObject], document.get("pages", [])):
            package = page.get("package_path")
            if not isinstance(package, str):
                continue
            evidence_path = f"{package}/evidence.json"
            payload, _ = read_attested_bytes(safe_path(root, evidence_path))
            evidence = loads_object(
                payload.decode("utf-8"), description="indexed page evidence"
            )
            expected.add(evidence_path)
            for artifact in cast(list[JsonObject], evidence.get("artifacts", [])):
                value = artifact.get("path")
                if isinstance(value, str):
                    expected.add(value)
        for bundle in cast(list[JsonObject], document.get("bundles", [])):
            value = bundle.get("path")
            if isinstance(value, str):
                expected.add(value)
