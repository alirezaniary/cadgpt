from __future__ import annotations

from pathlib import Path

import pytest
from cadgpt_regulations.workspace import (
    STAGE_NAMES,
    WorkspaceError,
    initialize_workspace,
)


def test_initialize_workspace_creates_private_stage_roots(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o755)
    parent = checkout / ".cadgpt"
    root = parent / "inbr"

    stages = initialize_workspace(root)

    assert tuple(stage.name for stage in stages) == STAGE_NAMES
    for path in (root, *stages):
        assert path.is_dir()
        assert path.stat().st_mode & 0o777 == 0o700


def test_initialize_workspace_is_idempotent(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o755)
    parent = checkout / ".cadgpt"
    root = parent / "inbr"

    first = initialize_workspace(root)
    modified = {path: path.stat().st_mtime_ns for path in (root, *first)}
    second = initialize_workspace(root)

    assert second == first
    assert {path: path.stat().st_mtime_ns for path in (root, *second)} == modified


def test_initialize_workspace_rejects_unsafe_existing_stage(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o755)
    parent = checkout / ".cadgpt"
    parent.mkdir(mode=0o700)
    root = parent / "inbr"
    root.mkdir(mode=0o700)
    unsafe_stage = root / "acquisition"
    unsafe_stage.mkdir(mode=0o777)
    unsafe_stage.chmod(0o777)

    with pytest.raises(WorkspaceError, match="group/world writable"):
        initialize_workspace(root)


def test_initialize_workspace_rejects_symlinked_root(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir(mode=0o755)
    parent = checkout / ".cadgpt"
    parent.mkdir(mode=0o700)
    real_root = parent / "real-inbr"
    real_root.mkdir(mode=0o700)
    root = parent / "inbr"
    root.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(WorkspaceError, match="not a real directory"):
        initialize_workspace(root)
