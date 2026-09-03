"""Safe, durable storage primitives for generated regulation evidence."""

from __future__ import annotations

import builtins
import ctypes
import errno
import hashlib
import os
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from cadgpt_regulations.errors import RegulationsError

_READ_CHUNK_SIZE = 1024 * 1024
_PROBE_SIZE = 4096


class StorageError(RegulationsError):
    """Raised when generated evidence cannot be stored or attested safely."""


class InstallStatus(StrEnum):
    """Whether an immutable payload was newly installed or already present."""

    INSTALLED = "installed"
    REUSED = "reused"


@dataclass(frozen=True)
class FileSnapshot:
    sha256: str
    bytes: int
    prefix: builtins.bytes
    device: int
    inode: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class FileInstallResult:
    status: InstallStatus
    snapshot: FileSnapshot


@dataclass(frozen=True)
class DirectoryEntry:
    path: str
    kind: str
    sha256: str | None
    bytes: int | None
    device: int
    inode: int


@dataclass(frozen=True)
class DirectorySnapshot:
    sha256: str
    files: int
    bytes: int
    entries: tuple[DirectoryEntry, ...]
    device: int
    inode: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class DirectoryInstallResult:
    status: InstallStatus
    snapshot: DirectorySnapshot


def validate_output_root(root: Path, *, description: str = "output root") -> None:
    """Require a caller-created, caller-owned, private real directory."""
    require_private_directory(root, description=description)


def ensure_private_directory(path: Path, *, description: str = "output directory") -> None:
    """Create one private directory and then re-attest it."""
    require_private_directory(path.parent, description=f"{description} parent")
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise StorageError(f"cannot create {description} {path}: {_os_error(exc)}") from exc
    require_private_directory(path, description=description)


def ensure_private_tree(root: Path, relative: str) -> Path:
    """Create a canonical relative directory tree without traversing symlinks."""
    validate_output_root(root)
    if relative in {"", "."}:
        return root
    target = safe_path(root, relative)
    current = root
    for index, _ in enumerate(target.relative_to(root).parts, start=1):
        value = Path(*target.relative_to(root).parts[:index]).as_posix()
        current = safe_path(root, value)
        ensure_private_directory(current)
    return current


def require_private_directory(path: Path, *, description: str) -> None:
    """Require a real directory owned by this process and not broadly writable."""
    _reject_any_symlink_component(
        path, description=description, expected_kind="real directory"
    )
    try:
        descriptor = _open_path_without_symlinks(
            path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
    except OSError as exc:
        raise StorageError(
            f"cannot inspect {description} {path}: {_os_error(exc)}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise StorageError(f"{description} is not a real directory: {path}")
        if metadata.st_uid != os.geteuid():
            raise StorageError(f"{description} is not owned by the current user: {path}")
        if metadata.st_mode & 0o022:
            raise StorageError(f"{description} is group/world writable: {path}")
    finally:
        os.close(descriptor)


def safe_path(root: Path, value: str) -> Path:
    """Resolve a strict POSIX relative path beneath a real, unsymlinked root."""
    require_private_directory(root, description="storage root")
    if not value or "\\" in value or "\x00" in value:
        raise StorageError(f"unsafe relative path: {value!r}")
    raw_parts = value.split("/")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or (raw_parts and len(raw_parts[0]) >= 2 and raw_parts[0][1] == ":")
    ):
        raise StorageError(f"unsafe relative path: {value!r}")
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise StorageError(f"relative path escapes root: {value!r}") from exc
    _reject_symlinked_ancestry(root, candidate)
    return candidate


def relative_path(root: Path, path: Path) -> str:
    """Return a POSIX relative path, rejecting paths outside ``root``."""
    try:
        value = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise StorageError(f"path escapes root: {path}") from exc
    safe_path(root, value)
    return value


def read_regular_snapshot(path: Path) -> FileSnapshot:
    """Hash a stable, caller-owned regular file without following symlinks."""
    _reject_any_symlink_component(path, description="path", expected_kind="regular file")
    try:
        initial = path.lstat()
    except OSError as exc:
        raise StorageError(f"cannot inspect regular file {path}: {_os_error(exc)}") from exc
    _validate_regular_metadata(initial, path)

    try:
        descriptor = _open_path_without_symlinks(path, os.O_RDONLY)
    except OSError as exc:
        raise StorageError(f"cannot open regular file {path}: {_os_error(exc)}") from exc

    digest = hashlib.sha256()
    prefix = b""
    byte_size = 0
    try:
        before = os.fstat(descriptor)
        _validate_regular_metadata(before, path)
        while chunk := os.read(descriptor, _READ_CHUNK_SIZE):
            if len(prefix) < _PROBE_SIZE:
                prefix += chunk[: _PROBE_SIZE - len(prefix)]
            digest.update(chunk)
            byte_size += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    _validate_regular_metadata(after, path)
    if _file_identity(before) != _file_identity(after) or byte_size != after.st_size:
        raise StorageError(f"regular file changed while it was read: {path}")
    snapshot = FileSnapshot(
        sha256=digest.hexdigest(),
        bytes=byte_size,
        prefix=prefix,
        device=after.st_dev,
        inode=after.st_ino,
        modified_ns=after.st_mtime_ns,
        changed_ns=after.st_ctime_ns,
    )
    if not file_snapshot_is_current(path, snapshot):
        raise StorageError(f"regular file identity changed after it was read: {path}")
    return snapshot


def read_attested_bytes(
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
) -> tuple[bytes, FileSnapshot]:
    """Read exact bytes through a stable no-follow descriptor and attest the result."""
    _reject_any_symlink_component(path, description="path", expected_kind="regular file")
    try:
        descriptor = _open_path_without_symlinks(path, os.O_RDONLY)
    except OSError as exc:
        raise StorageError(f"cannot open regular file {path}: {_os_error(exc)}") from exc
    digest = hashlib.sha256()
    payload = bytearray()
    prefix = b""
    try:
        before = os.fstat(descriptor)
        _validate_regular_metadata(before, path)
        while chunk := os.read(descriptor, _READ_CHUNK_SIZE):
            if len(prefix) < _PROBE_SIZE:
                prefix += chunk[: _PROBE_SIZE - len(prefix)]
            payload.extend(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if _file_identity(before) != _file_identity(after) or len(payload) != after.st_size:
        raise StorageError(f"regular file changed while it was read: {path}")
    snapshot = FileSnapshot(
        sha256=digest.hexdigest(),
        bytes=len(payload),
        prefix=prefix,
        device=after.st_dev,
        inode=after.st_ino,
        modified_ns=after.st_mtime_ns,
        changed_ns=after.st_ctime_ns,
    )
    if not file_snapshot_is_current(path, snapshot):
        raise StorageError(f"regular file identity changed after it was read: {path}")
    if expected_sha256 is not None and snapshot.sha256 != expected_sha256:
        raise StorageError(f"regular file digest differs from expectation: {path}")
    if expected_bytes is not None and snapshot.bytes != expected_bytes:
        raise StorageError(f"regular file size differs from expectation: {path}")
    return bytes(payload), snapshot


def file_snapshot_is_current(path: Path, snapshot: FileSnapshot) -> bool:
    try:
        descriptor = _open_path_without_symlinks(path, os.O_RDONLY)
        try:
            current = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        _validate_regular_metadata(current, path)
    except (OSError, StorageError):
        return False
    return _file_identity(current) == (
        snapshot.device,
        snapshot.inode,
        snapshot.bytes,
        snapshot.modified_ns,
        snapshot.changed_ns,
        current.st_uid,
        current.st_mode,
        1,
    )


def install_immutable_bytes(
    destination: Path,
    payload: bytes,
    *,
    expected_sha256: str | None = None,
) -> FileInstallResult:
    """Durably install exact bytes once, reusing only identical existing content."""
    _validate_destination_leaf(destination)
    require_private_directory(destination.parent, description="payload directory")
    digest = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise StorageError("payload digest differs from the expected SHA-256")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    installed = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        result = install_temporary_file(temporary, destination, expected_sha256=digest)
        installed = True
        return result
    except OSError as exc:
        raise StorageError(
            f"cannot create immutable payload {destination}: {_os_error(exc)}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not installed:
            _unlink_regular_identity(temporary, _identity_if_regular(temporary))


def install_temporary_file(
    temporary: Path,
    destination: Path,
    *,
    expected_sha256: str,
) -> FileInstallResult:
    """Install an existing temporary regular file using hard-link no-clobber semantics."""
    if temporary == destination:
        raise StorageError("temporary and destination files must differ")
    _validate_destination_leaf(destination)
    require_private_directory(temporary.parent, description="temporary payload directory")
    require_private_directory(destination.parent, description="payload directory")
    temporary_snapshot = read_regular_snapshot(temporary)
    if temporary_snapshot.sha256 != expected_sha256:
        raise StorageError("temporary payload digest differs from the expected SHA-256")

    try:
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        existing = _matching_existing_file(destination, temporary_snapshot)
        _unlink_regular_identity(
            temporary, (temporary_snapshot.device, temporary_snapshot.inode)
        )
        return FileInstallResult(InstallStatus.REUSED, existing)
    except OSError as exc:
        raise StorageError(
            f"cannot install immutable payload {destination}: {_os_error(exc)}"
        ) from exc

    installed_identity = (temporary_snapshot.device, temporary_snapshot.inode)
    try:
        installed = destination.lstat()
        if (
            not stat.S_ISREG(installed.st_mode)
            or stat.S_ISLNK(installed.st_mode)
            or (installed.st_dev, installed.st_ino) != installed_identity
        ):
            raise StorageError(f"installed payload identity changed: {destination}")
        _unlink_regular_identity(temporary, installed_identity)
        fsync_directory(destination.parent)
        final_snapshot = read_regular_snapshot(destination)
        if final_snapshot.sha256 != expected_sha256:
            raise StorageError(
                f"installed payload failed digest attestation: {destination}"
            )
        return FileInstallResult(InstallStatus.INSTALLED, final_snapshot)
    except (OSError, StorageError):
        _unlink_regular_identity(destination, installed_identity)
        with suppress(StorageError):
            fsync_directory(destination.parent)
        raise


def stage_attested_copy(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
) -> FileSnapshot:
    """Copy an attested source through stable descriptors into a private work file."""
    _validate_destination_leaf(destination)
    require_private_directory(destination.parent, description="staging directory")
    _reject_any_symlink_component(
        source, description="source path", expected_kind="regular file"
    )
    try:
        source_descriptor = _open_path_without_symlinks(source, os.O_RDONLY)
    except OSError as exc:
        raise StorageError(f"cannot open source file {source}: {_os_error(exc)}") from exc
    destination_descriptor = -1
    source_digest = hashlib.sha256()
    source_bytes = 0
    try:
        before = os.fstat(source_descriptor)
        _validate_regular_metadata(before, source)
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        while chunk := os.read(source_descriptor, _READ_CHUNK_SIZE):
            source_digest.update(chunk)
            source_bytes += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
        os.fsync(destination_descriptor)
        after = os.fstat(source_descriptor)
    except OSError as exc:
        raise StorageError(f"cannot stage source file {source}: {_os_error(exc)}") from exc
    finally:
        os.close(source_descriptor)
        if destination_descriptor >= 0:
            os.close(destination_descriptor)

    digest = source_digest.hexdigest()
    if _file_identity(before) != _file_identity(after) or source_bytes != after.st_size:
        _unlink_regular_identity(destination, _identity_if_regular(destination))
        raise StorageError(f"source file changed while it was staged: {source}")
    source_snapshot = FileSnapshot(
        sha256=digest,
        bytes=source_bytes,
        prefix=b"",
        device=after.st_dev,
        inode=after.st_ino,
        modified_ns=after.st_mtime_ns,
        changed_ns=after.st_ctime_ns,
    )
    if (
        digest != expected_sha256
        or source_bytes != expected_bytes
        or not file_snapshot_is_current(source, source_snapshot)
    ):
        _unlink_regular_identity(destination, _identity_if_regular(destination))
        raise StorageError(f"source file failed staging re-attestation: {source}")
    staged = read_regular_snapshot(destination)
    if staged.sha256 != expected_sha256 or staged.bytes != expected_bytes:
        _unlink_regular_identity(destination, (staged.device, staged.inode))
        raise StorageError(f"staged source differs from its attested input: {source}")
    return staged


def make_temporary_directory(parent: Path, *, prefix: str = ".package.") -> Path:
    """Create a private sibling directory suitable for terminal installation."""
    if not prefix or any(character in prefix for character in ("/", "\\", "\x00")):
        raise StorageError(f"unsafe temporary package prefix: {prefix!r}")
    require_private_directory(parent, description="package parent directory")
    try:
        temporary = Path(tempfile.mkdtemp(prefix=prefix, suffix=".tmp", dir=parent))
        temporary.chmod(0o700)
    except OSError as exc:
        raise StorageError(f"cannot create temporary package: {_os_error(exc)}") from exc
    require_private_directory(temporary, description="temporary package directory")
    return temporary


def snapshot_directory(path: Path) -> DirectorySnapshot:
    """Hash a safe directory tree without links or special files."""
    require_private_directory(path, description="terminal package directory")
    root_metadata = path.lstat()
    entries: list[DirectoryEntry] = []
    _scan_directory(path, path, entries)
    encoded = bytearray()
    files = 0
    byte_size = 0
    for entry in entries:
        encoded.extend(entry.kind.encode("ascii"))
        encoded.extend(b"\0")
        encoded.extend(entry.path.encode("utf-8"))
        encoded.extend(b"\0")
        if entry.kind == "file":
            assert entry.sha256 is not None and entry.bytes is not None
            encoded.extend(entry.sha256.encode("ascii"))
            encoded.extend(b"\0")
            encoded.extend(str(entry.bytes).encode("ascii"))
            files += 1
            byte_size += entry.bytes
        encoded.extend(b"\n")
    current = path.lstat()
    if _directory_identity(root_metadata) != _directory_identity(current):
        raise StorageError(f"terminal package changed while it was read: {path}")
    return DirectorySnapshot(
        sha256=hashlib.sha256(encoded).hexdigest(),
        files=files,
        bytes=byte_size,
        entries=tuple(entries),
        device=current.st_dev,
        inode=current.st_ino,
        modified_ns=current.st_mtime_ns,
        changed_ns=current.st_ctime_ns,
    )


def install_terminal_directory(
    temporary: Path,
    destination: Path,
    *,
    required_file: str | None = None,
) -> DirectoryInstallResult:
    """Atomically publish a complete directory, never replacing an existing package."""
    if temporary == destination:
        raise StorageError("temporary and terminal package directories must differ")
    if temporary.parent != destination.parent:
        raise StorageError("temporary and terminal package directories must be siblings")
    _validate_destination_leaf(destination)
    require_private_directory(destination.parent, description="package parent directory")
    temporary_snapshot = snapshot_directory(temporary)
    if required_file is not None:
        required = safe_path(temporary, required_file)
        read_regular_snapshot(required)

    existing = _existing_directory(destination)
    if existing is not None:
        return _reuse_terminal_directory(
            temporary, destination, temporary_snapshot, existing
        )

    _fsync_tree(temporary)
    refreshed = snapshot_directory(temporary)
    if refreshed.sha256 != temporary_snapshot.sha256 or (
        refreshed.device,
        refreshed.inode,
    ) != (temporary_snapshot.device, temporary_snapshot.inode):
        raise StorageError(f"temporary package changed before installation: {temporary}")
    try:
        _rename_no_replace(temporary, destination)
    except FileExistsError as exc:
        raced = _existing_directory(destination)
        if raced is not None:
            return _reuse_terminal_directory(
                temporary, destination, temporary_snapshot, raced
            )
        raise StorageError(f"terminal package destination raced: {destination}") from exc
    except OSError as exc:
        raise StorageError(
            f"cannot install terminal package {destination}: {_os_error(exc)}"
        ) from exc

    try:
        installed = destination.lstat()
        if (
            not stat.S_ISDIR(installed.st_mode)
            or stat.S_ISLNK(installed.st_mode)
            or (installed.st_dev, installed.st_ino)
            != (temporary_snapshot.device, temporary_snapshot.inode)
        ):
            raise StorageError(f"installed package identity changed: {destination}")
        fsync_directory(destination.parent)
        final_snapshot = snapshot_directory(destination)
        if final_snapshot.sha256 != temporary_snapshot.sha256:
            raise StorageError(f"installed package failed tree attestation: {destination}")
        return DirectoryInstallResult(InstallStatus.INSTALLED, final_snapshot)
    except OSError as exc:
        raise StorageError(
            f"cannot attest installed terminal package {destination}: {_os_error(exc)}"
        ) from exc


def fsync_directory(path: Path) -> None:
    """Persist directory entry changes where the platform supports directory fsync."""
    require_private_directory(path, description="directory to synchronize")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise StorageError(
            f"cannot synchronize directory {path}: {_os_error(exc)}"
        ) from exc


def _matching_existing_file(destination: Path, expected: FileSnapshot) -> FileSnapshot:
    try:
        existing = read_regular_snapshot(destination)
    except StorageError as exc:
        raise StorageError(f"existing destination is unsafe: {destination}: {exc}") from exc
    if existing.sha256 != expected.sha256 or existing.bytes != expected.bytes:
        raise StorageError(
            f"existing destination differs and was not overwritten: {destination}"
        )
    return existing


def _existing_directory(path: Path) -> DirectorySnapshot | None:
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StorageError(
            f"cannot inspect terminal package {path}: {_os_error(exc)}"
        ) from exc
    try:
        return snapshot_directory(path)
    except StorageError as exc:
        raise StorageError(f"existing terminal package is unsafe: {path}: {exc}") from exc


def _reuse_terminal_directory(
    temporary: Path,
    destination: Path,
    expected: DirectorySnapshot,
    existing: DirectorySnapshot,
) -> DirectoryInstallResult:
    if existing.sha256 != expected.sha256:
        raise StorageError(
            f"existing terminal package differs and was not overwritten: {destination}"
        )
    _remove_attested_temporary_directory(temporary, expected)
    return DirectoryInstallResult(InstallStatus.REUSED, existing)


def _scan_directory(root: Path, directory: Path, entries: list[DirectoryEntry]) -> None:
    before = directory.lstat()
    _validate_directory_metadata(before, directory)
    try:
        children = sorted(directory.iterdir(), key=lambda child: child.name)
    except OSError as exc:
        raise StorageError(
            f"cannot enumerate package directory {directory}: {_os_error(exc)}"
        ) from exc
    for child in children:
        relative = relative_path(root, child)
        try:
            metadata = child.lstat()
        except OSError as exc:
            raise StorageError(
                f"cannot inspect package entry {child}: {_os_error(exc)}"
            ) from exc
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            _validate_directory_metadata(metadata, child)
            entries.append(
                DirectoryEntry(
                    relative,
                    "directory",
                    None,
                    None,
                    metadata.st_dev,
                    metadata.st_ino,
                )
            )
            _scan_directory(root, child, entries)
            continue
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise StorageError(f"package entry is not a regular file: {child}")
        snapshot = read_regular_snapshot(child)
        entries.append(
            DirectoryEntry(
                relative,
                "file",
                snapshot.sha256,
                snapshot.bytes,
                snapshot.device,
                snapshot.inode,
            )
        )
    after = directory.lstat()
    _validate_directory_metadata(after, directory)
    if _directory_identity(before) != _directory_identity(after):
        raise StorageError(f"package directory changed while it was read: {directory}")


def _fsync_tree(root: Path) -> None:
    directories: list[Path] = []
    for directory_name, child_directories, filenames in os.walk(root, topdown=True):
        current = Path(directory_name)
        directories.append(current)
        child_directories.sort()
        filenames.sort()
        for filename in filenames:
            path = current / filename
            snapshot = read_regular_snapshot(path)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(path, flags)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError as exc:
                raise StorageError(
                    f"cannot synchronize package file {path}: {_os_error(exc)}"
                ) from exc
            if not file_snapshot_is_current(path, snapshot):
                raise StorageError(f"package file changed while synchronizing: {path}")
    for directory in reversed(directories):
        fsync_directory(directory)


def _remove_attested_temporary_directory(path: Path, expected: DirectorySnapshot) -> None:
    current = snapshot_directory(path)
    if (
        current.sha256 != expected.sha256
        or (current.device, current.inode)
        != (
            expected.device,
            expected.inode,
        )
        or current.entries != expected.entries
    ):
        raise StorageError(f"temporary package changed before cleanup: {path}")
    try:
        descriptor = _open_path_without_symlinks(
            path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (expected.device, expected.inode):
                raise StorageError(f"temporary package changed before cleanup: {path}")
            _remove_directory_contents_by_fd(
                descriptor,
                expected={entry.path: entry for entry in expected.entries},
                prefix="",
            )
        finally:
            os.close(descriptor)
        current_root = path.lstat()
        if (current_root.st_dev, current_root.st_ino) != (
            expected.device,
            expected.inode,
        ):
            raise StorageError(f"temporary package changed before cleanup: {path}")
        path.rmdir()
        fsync_directory(path.parent)
    except OSError as exc:
        raise StorageError(
            f"cannot remove reused temporary package: {_os_error(exc)}"
        ) from exc


def _remove_directory_contents_by_fd(
    descriptor: int, *, expected: dict[str, DirectoryEntry], prefix: str
) -> None:
    names = sorted(os.listdir(descriptor))
    for name in names:
        relative = f"{prefix}/{name}" if prefix else name
        entry = expected.get(relative)
        if entry is None:
            raise StorageError(
                f"temporary package gained an entry before cleanup: {relative}"
            )
        metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != (entry.device, entry.inode):
            raise StorageError(
                f"temporary package entry changed before cleanup: {relative}"
            )
        if entry.kind == "directory":
            child = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                _remove_directory_contents_by_fd(child, expected=expected, prefix=relative)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=descriptor)
        elif entry.kind == "file" and stat.S_ISREG(metadata.st_mode):
            os.unlink(name, dir_fd=descriptor)
        else:
            raise StorageError(
                f"temporary package entry changed before cleanup: {relative}"
            )


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Publish a directory atomically without POSIX rename replacement semantics."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise StorageError("renameat2 is required for no-replace directory publication")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    at_fdcwd = -100
    rename_noreplace = 1
    result = renameat2(
        at_fdcwd,
        os.fsencode(source),
        at_fdcwd,
        os.fsencode(destination),
        rename_noreplace,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def _validate_regular_metadata(metadata: os.stat_result, path: Path) -> None:
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise StorageError(f"path is not a regular file: {path}")
    if metadata.st_uid != os.geteuid():
        raise StorageError(f"regular file is not owned by the current user: {path}")
    if metadata.st_nlink != 1:
        raise StorageError(f"regular file must have exactly one hard link: {path}")
    if metadata.st_mode & 0o022:
        raise StorageError(f"regular file is group/world writable: {path}")


def _validate_directory_metadata(metadata: os.stat_result, path: Path) -> None:
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise StorageError(f"path is not a real directory: {path}")
    if metadata.st_uid != os.geteuid():
        raise StorageError(f"directory is not owned by the current user: {path}")
    if metadata.st_mode & 0o022:
        raise StorageError(f"directory is group/world writable: {path}")


def _reject_symlinked_ancestry(root: Path, candidate: Path) -> None:
    relative = candidate.relative_to(root)
    current = root
    parts = relative.parts
    for index, part in enumerate(parts):
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StorageError(
                f"cannot inspect storage path component {current}: {_os_error(exc)}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise StorageError(f"storage path contains a symlink: {current}")
        if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            raise StorageError(f"storage path component is not a directory: {current}")


def _reject_any_symlink_component(
    path: Path, *, description: str, expected_kind: str
) -> None:
    """Reject symlinks in a path before opening it component by component."""
    absolute = _lexical_absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise StorageError(
                f"cannot inspect {description} path component {current}: {_os_error(exc)}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise StorageError(
                f"{description} is not a {expected_kind} because its path contains "
                f"a symlink: {current}"
            )


def _open_path_without_symlinks(path: Path, flags: int) -> int:
    """Open a path through no-follow directory descriptors to close ancestor races."""
    absolute = _lexical_absolute(path)
    parts = absolute.parts[1:]
    if not parts:
        return os.open(absolute.anchor, flags | getattr(os, "O_NOFOLLOW", 0))
    directory_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    parent = os.open(absolute.anchor, directory_flags)
    try:
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        return os.open(parts[-1], flags | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
    finally:
        os.close(parent)


def _lexical_absolute(path: Path) -> Path:
    absolute = path if path.is_absolute() else Path.cwd() / path
    if any(part in {".", ".."} for part in absolute.parts):
        raise StorageError(f"path is not lexically canonical: {path}")
    return absolute


def _validate_destination_leaf(destination: Path) -> None:
    if destination.name in {"", ".", ".."}:
        raise StorageError(f"unsafe destination path: {destination}")


def _file_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_uid,
        metadata.st_mode,
        metadata.st_nlink,
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_uid,
        metadata.st_mode,
    )


def _identity_if_regular(path: Path) -> tuple[int, int] | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
        return metadata.st_dev, metadata.st_ino
    return None


def _unlink_regular_identity(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        current = path.lstat()
        if (
            stat.S_ISREG(current.st_mode)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino) == identity
        ):
            path.unlink()
    except OSError:
        return


def _os_error(exc: OSError) -> str:
    return f"{type(exc).__name__}: {exc.strerror or 'operating system error'}"
