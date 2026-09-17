"""Access package-owned schemas and catalog data."""

from __future__ import annotations

from importlib import resources

from cadgpt_regulations.jsonio import JsonObject, loads_object


def load_packaged_json(package: str, filename: str) -> JsonObject:
    resource = resources.files(package).joinpath(filename)
    return loads_object(
        resource.read_text(encoding="utf-8"),
        description=f"packaged resource {package}/{filename}",
    )
