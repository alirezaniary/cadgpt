from __future__ import annotations

import hashlib
import os
from pathlib import Path

import cadgpt_regulations.storage as storage_module
import pytest
from cadgpt_regulations.storage import (
    InstallStatus,
    StorageError,
    ensure_private_directory,
    install_immutable_bytes,
    install_temporary_file,
    install_terminal_directory,
    make_temporary_directory,
    read_regular_snapshot,
    relative_path,
    safe_path,
    snapshot_directory,
    stage_attested_copy,
    validate_output_root,
)


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _private_file(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def test_output_root_and_created_directories_must_be_real_owned_and_private(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "root")
    validate_output_root(root)
    child = root / "pages"
    ensure_private_directory(child)
    assert stat_mode(child) == 0o700

    child.chmod(0o777)
    with pytest.raises(StorageError, match="group/world writable"):
        validate_output_root(child)

    victim = _private_directory(tmp_path / "victim")
    linked = tmp_path / "linked-root"
    linked.symlink_to(victim, target_is_directory=True)
    with pytest.raises(StorageError, match="not a real directory"):
        validate_output_root(linked)


def test_output_root_rejects_a_symlinked_ancestor(tmp_path: Path) -> None:
    real_parent = _private_directory(tmp_path / "real-parent")
    root = _private_directory(real_parent / "root")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(StorageError, match="contains a symlink"):
        validate_output_root(linked_parent / root.name)


def test_regular_snapshot_rejects_a_symlinked_ancestor(tmp_path: Path) -> None:
    real_parent = _private_directory(tmp_path / "real-parent")
    source = _private_file(real_parent / "source", b"evidence")
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(StorageError, match="contains a symlink"):
        read_regular_snapshot(linked_parent / source.name)


@pytest.mark.parametrize(
    "value",
    ["", "/absolute", "../escape", "a/../escape", "./page", "a//b", "a/", "C:/x", "a\\b"],
)
def test_safe_paths_reject_traversal_and_noncanonical_separators(
    tmp_path: Path, value: str
) -> None:
    root = _private_directory(tmp_path / "root")
    with pytest.raises(StorageError, match="unsafe relative path"):
        safe_path(root, value)


def test_safe_paths_preserve_unicode_and_reject_paths_outside_root(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "root")
    path = safe_path(root, "pages/صفحه-one/evidence.json")
    assert path == root / "pages" / "صفحه-one" / "evidence.json"
    assert relative_path(root, path) == "pages/صفحه-one/evidence.json"

    with pytest.raises(StorageError, match="escapes root"):
        relative_path(root, tmp_path / "outside")

    outside = _private_directory(tmp_path / "outside-directory")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(StorageError, match="contains a symlink"):
        safe_path(root, "linked/evidence.json")


def test_regular_snapshot_rejects_symlink_fifo_and_hardlink(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "root")
    source = _private_file(root / "source", b"evidence")
    snapshot = read_regular_snapshot(source)
    assert snapshot.sha256 == hashlib.sha256(b"evidence").hexdigest()
    assert snapshot.bytes == 8

    symlink = root / "symlink"
    symlink.symlink_to(source)
    with pytest.raises(StorageError, match="not a regular file"):
        read_regular_snapshot(symlink)

    fifo = root / "fifo"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(StorageError, match="not a regular file"):
        read_regular_snapshot(fifo)

    hardlink = root / "hardlink"
    os.link(source, hardlink)
    with pytest.raises(StorageError, match="exactly one hard link"):
        read_regular_snapshot(source)


def test_immutable_file_install_is_no_clobber_and_reuses_without_rewrite(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "root")
    destination = root / "evidence.json"
    first = install_immutable_bytes(destination, b'{"ready":true}\n')
    identity = destination.stat().st_ino
    modified = destination.stat().st_mtime_ns

    second = install_immutable_bytes(destination, b'{"ready":true}\n')

    assert first.status is InstallStatus.INSTALLED
    assert second.status is InstallStatus.REUSED
    assert destination.stat().st_ino == identity
    assert destination.stat().st_mtime_ns == modified
    assert destination.read_bytes() == b'{"ready":true}\n'
    assert stat_mode(destination) == 0o600

    with pytest.raises(StorageError, match="differs and was not overwritten"):
        install_immutable_bytes(destination, b'{"ready":false}\n')
    assert destination.read_bytes() == b'{"ready":true}\n'


def test_immutable_file_install_rejects_existing_symlink_without_touching_victim(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "root")
    victim = _private_file(tmp_path / "victim", b"victim")
    destination = root / "evidence.json"
    destination.symlink_to(victim)

    with pytest.raises(StorageError, match="existing destination is unsafe"):
        install_immutable_bytes(destination, b"replacement")

    assert victim.read_bytes() == b"victim"
    assert destination.is_symlink()


def test_temporary_file_and_destination_must_differ(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "root")
    temporary = _private_file(root / "temporary", b"payload")

    with pytest.raises(StorageError, match="must differ"):
        install_temporary_file(
            temporary,
            temporary,
            expected_sha256=hashlib.sha256(b"payload").hexdigest(),
        )
    assert temporary.read_bytes() == b"payload"


def test_attested_source_copy_is_exact_and_rejects_drift(tmp_path: Path) -> None:
    source_root = _private_directory(tmp_path / "source-root")
    work_root = _private_directory(tmp_path / "work-root")
    source = _private_file(source_root / "source.pdf", b"%PDF-attested")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    staged = stage_attested_copy(
        source,
        work_root / "source.pdf",
        expected_sha256=digest,
        expected_bytes=len(b"%PDF-attested"),
    )
    assert staged.sha256 == digest
    assert (work_root / "source.pdf").read_bytes() == source.read_bytes()

    with pytest.raises(StorageError, match="failed staging re-attestation"):
        stage_attested_copy(
            source,
            work_root / "wrong.pdf",
            expected_sha256="0" * 64,
            expected_bytes=len(b"%PDF-attested"),
        )
    assert not (work_root / "wrong.pdf").exists()


def test_terminal_directory_install_is_atomic_reusable_and_no_clobber(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "root")
    destination = root / "page-package"
    first_temporary = _package(root, b"raw text", b"render")
    first = install_terminal_directory(
        first_temporary, destination, required_file="evidence.json"
    )
    identity = destination.stat().st_ino
    modified = destination.stat().st_mtime_ns

    second_temporary = _package(root, b"raw text", b"render")
    second = install_terminal_directory(
        second_temporary, destination, required_file="evidence.json"
    )

    assert first.status is InstallStatus.INSTALLED
    assert second.status is InstallStatus.REUSED
    assert not second_temporary.exists()
    assert destination.stat().st_ino == identity
    assert destination.stat().st_mtime_ns == modified
    assert first.snapshot.sha256 == second.snapshot.sha256

    conflicting = _package(root, b"changed text", b"render")
    with pytest.raises(StorageError, match="differs and was not overwritten"):
        install_terminal_directory(conflicting, destination)
    assert conflicting.is_dir()
    assert (destination / "raw.txt").read_bytes() == b"raw text"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "fifo", "hardlink"])
def test_terminal_directory_rejects_unsafe_entries(
    tmp_path: Path, unsafe_kind: str
) -> None:
    root = _private_directory(tmp_path / "root")
    temporary = make_temporary_directory(root)
    source = _private_file(temporary / "source", b"source")
    unsafe = temporary / "unsafe"
    if unsafe_kind == "symlink":
        unsafe.symlink_to(source)
    elif unsafe_kind == "fifo":
        os.mkfifo(unsafe, mode=0o600)
    else:
        os.link(source, unsafe)

    expected = {
        "symlink": "contains a symlink",
        "fifo": "not a regular file",
        "hardlink": "exactly one hard link",
    }[unsafe_kind]
    with pytest.raises(StorageError, match=expected):
        install_terminal_directory(temporary, root / "terminal")
    assert temporary.is_dir()


def test_terminal_directory_requires_a_sibling_temporary_and_real_destination(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "root")
    other = _private_directory(tmp_path / "other")
    temporary = _package(other, b"raw", b"render")
    with pytest.raises(StorageError, match="must be siblings"):
        install_terminal_directory(temporary, root / "terminal")

    local_temporary = _package(root, b"raw", b"render")
    victim = _private_directory(tmp_path / "victim")
    destination = root / "terminal"
    destination.symlink_to(victim, target_is_directory=True)
    with pytest.raises(StorageError, match="existing terminal package is unsafe"):
        install_terminal_directory(local_temporary, destination)
    assert destination.is_symlink()

    same = _package(root, b"raw", b"render")
    with pytest.raises(StorageError, match="must differ"):
        install_terminal_directory(same, same)
    assert same.is_dir()


def test_terminal_directory_publish_never_replaces_a_raced_empty_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _private_directory(tmp_path / "root")
    temporary = _package(root, b"raw", b"render")
    destination = _private_directory(root / "terminal")
    destination_inode = destination.stat().st_ino
    real_existing = storage_module._existing_directory
    calls = 0

    def hide_first_existing(path: Path):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return real_existing(path)

    monkeypatch.setattr(storage_module, "_existing_directory", hide_first_existing)
    with pytest.raises(StorageError, match="differs and was not overwritten"):
        install_terminal_directory(temporary, destination)

    assert destination.stat().st_ino == destination_inode
    assert list(destination.iterdir()) == []
    assert temporary.is_dir()


def test_reuse_cleanup_does_not_delete_a_same_uid_swapped_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _private_directory(tmp_path / "root")
    destination = root / "terminal"
    first = _package(root, b"raw", b"render")
    install_terminal_directory(first, destination)
    temporary = _package(root, b"raw", b"render")
    parked = root / "parked"
    victim = _private_directory(root / "victim")
    victim_file = _private_file(victim / "important", b"keep")
    real_snapshot = storage_module.snapshot_directory
    temporary_snapshots = 0

    def swap_before_cleanup(path: Path):  # type: ignore[no-untyped-def]
        nonlocal temporary_snapshots
        if path == temporary:
            temporary_snapshots += 1
            if temporary_snapshots == 2:
                temporary.rename(parked)
                victim.rename(temporary)
        return real_snapshot(path)

    monkeypatch.setattr(storage_module, "snapshot_directory", swap_before_cleanup)
    with pytest.raises(StorageError, match="changed before cleanup"):
        install_terminal_directory(temporary, destination)

    assert (temporary / victim_file.name).read_bytes() == b"keep"


def test_terminal_directory_requires_a_safe_terminal_record(tmp_path: Path) -> None:
    root = _private_directory(tmp_path / "root")
    temporary = _package(root, b"raw", b"render")
    with pytest.raises(StorageError, match="unsafe relative path"):
        install_terminal_directory(
            temporary,
            root / "terminal",
            required_file="../outside.json",
        )
    assert temporary.is_dir()


def test_directory_snapshot_is_deterministic_and_accounts_empty_directories(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "root")
    first = _package(root, b"raw", b"render")
    second = _package(root, b"raw", b"render")
    _private_directory(first / "empty")
    _private_directory(second / "empty")

    first_snapshot = snapshot_directory(first)
    second_snapshot = snapshot_directory(second)

    assert first_snapshot.sha256 == second_snapshot.sha256
    assert first_snapshot.files == 3
    assert first_snapshot.bytes == len(b"rawrenderevidence")
    assert any(
        entry.path == "empty" and entry.kind == "directory"
        for entry in first_snapshot.entries
    )


def _package(parent: Path, raw: bytes, render: bytes) -> Path:
    package = make_temporary_directory(parent)
    _private_file(package / "raw.txt", raw)
    _private_file(package / "render.png", render)
    _private_file(package / "evidence.json", b"evidence")
    return package


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777
