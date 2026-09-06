"""Initialize the durable local workspace for INBR pipeline artifacts."""

from __future__ import annotations

from pathlib import Path

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.storage import ensure_private_directory, validate_output_root


class WorkspaceError(RegulationsError):
    """Raised when the durable INBR workspace cannot be prepared safely."""


STAGE_NAMES = (
    "acquisition",
    "transcription",
    "structure",
    "extraction",
    "validation",
    "publication",
)


def initialize_workspace(root: Path) -> tuple[Path, ...]:
    """Create and attest the private output roots used by one INBR pipeline run."""
    try:
        _ensure_private_workspace_parent(root.parent)
        ensure_private_directory(root, description="INBR workspace")
        stages = tuple(root / stage for stage in STAGE_NAMES)
        for stage in stages:
            ensure_private_directory(stage, description=f"INBR {stage} workspace")
            validate_output_root(stage, description=f"INBR {stage} workspace")
    except RegulationsError as exc:
        raise WorkspaceError(str(exc)) from exc
    return stages


def _ensure_private_workspace_parent(path: Path) -> None:
    """Create the ignored `.cadgpt` directory without constraining its checkout parent."""
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise WorkspaceError(f"cannot create INBR workspace parent {path}: {exc}") from exc
    validate_output_root(path, description="INBR workspace parent")
