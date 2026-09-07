from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.cli import _parser, _resolve_root_arguments, main
from cadgpt_regulations.inventory import build_inventory, write_inventory
from cadgpt_regulations.jsonio import JsonObject, canonical_bytes


def test_workspace_command_creates_durable_stage_roots(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o755)
    root = checkout / ".cadgpt" / "inbr"

    assert main(["workspace", "--root", str(root)]) == 0

    stages = sorted(root.iterdir())
    assert [path.name for path in stages] == [
        "acquisition",
        "extraction",
        "publication",
        "structure",
        "transcription",
        "validation",
    ]
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in stages)


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


@pytest.mark.parametrize(
    ("argv", "root_attrs"),
    [
        (
            ["page-probe", "--acquisition", "acquisition.json", "--root", "acq-root",
             "--output-root", "probe-root"],
            ["root", "output_root"],
        ),
        (
            ["transcribe", "--probe", "probe.json", "--root", "run-root"],
            ["root"],
        ),
        (
            ["structure", "--transcription", "transcription.json", "--root", "run-root",
             "--output-root", "structure-root"],
            ["root", "output_root"],
        ),
        (
            ["extract-jobs", "--transcription", "transcription.json", "--root", "run-root",
             "--structure", "structure.json", "--structure-root", "structure-root",
             "--output-root", "extraction-root"],
            ["root", "structure_root", "output_root"],
        ),
    ],
)
def test_resolve_root_arguments_makes_every_root_path_absolute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    root_attrs: list[str],
) -> None:
    """Regression test for F2: a relative --output-root failed every page.

    `tempfile.mkdtemp()` always returns an absolute path even when given a
    relative `dir=`, so a relative root failed the sibling check in
    `storage.install_terminal_directory` even when the two directories really
    were siblings (see test_storage.py for that mechanism). The CLI now
    resolves every "*root" argument once at the boundary, for every affected
    subcommand, instead of patching the comparison deep in storage.py.
    """
    monkeypatch.chdir(tmp_path)
    args = _parser().parse_args(argv)
    for attr in root_attrs:
        assert not cast(Path, getattr(args, attr)).is_absolute()

    _resolve_root_arguments(args)

    for attr in root_attrs:
        value = cast(Path, getattr(args, attr))
        assert value.is_absolute()
        assert value.parent == tmp_path
    # A file argument that is not named "*root" is left untouched: resolving it
    # would silently follow a symlink past `_load_receipt`'s own rejection of one.
    file_attr = {
        "page-probe": "acquisition",
        "transcribe": "probe",
        "structure": "transcription",
        "extract-jobs": "transcription",
    }[argv[0]]
    assert not cast(Path, getattr(args, file_attr)).is_absolute()
