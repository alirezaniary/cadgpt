from __future__ import annotations

from pathlib import Path
from typing import cast

from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.cli import main
from cadgpt_regulations.inventory import build_inventory, write_inventory
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes


def test_validate_and_publish_check_honor_custom_catalog(tmp_path: Path) -> None:
    source = tmp_path / "corpus"
    source.mkdir()
    catalog = load_catalog()
    first = cast(list[JsonObject], catalog["families"])[0]
    first["title_en"] = "Definitions (custom contract)"
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(canonical_bytes(catalog))
    manifest_path = tmp_path / "manifest.json"
    write_inventory(build_inventory(source, catalog=catalog), manifest_path)

    assert main(["validate", str(manifest_path), "--catalog", str(catalog_path)]) == 0
    assert main(["publish-check", str(manifest_path), "--catalog", str(catalog_path)]) == 1
    assert main(["validate", str(manifest_path)]) == 2
