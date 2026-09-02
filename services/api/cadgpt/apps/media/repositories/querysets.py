from __future__ import annotations

from typing import TYPE_CHECKING, Self

from cadgpt.apps.base.querysets import TenantScopedQuerySet

if TYPE_CHECKING:
    # Imported for the quoted type parameter on the queryset below, which ruff
    # does not read as a use. Importing at runtime would be a cycle: the model
    # module imports the manager, which imports this one.
    from cadgpt.apps.media.models import Media  # noqa: F401


class MediaQuerySet(TenantScopedQuerySet["Media"]):
    def of_kind(self, kind: str) -> Self:
        return self.filter(kind=kind)

    def with_checksum(self, checksum: str) -> Self:
        return self.filter(checksum_sha256=checksum)

    def with_uploader(self) -> Self:
        return self.select_related("uploaded_by")
