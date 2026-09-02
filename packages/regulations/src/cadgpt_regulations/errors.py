"""Typed failures at the corpus package boundary."""


class RegulationsError(Exception):
    """Base class for expected command failures."""


class CatalogError(RegulationsError):
    """The curated catalog is structurally or semantically invalid."""


class InventoryError(RegulationsError):
    """The requested inventory cannot be started or written."""


class ManifestError(RegulationsError):
    """A manifest violates its schema or deterministic invariants."""
