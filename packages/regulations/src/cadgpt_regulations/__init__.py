"""Regulation corpus inventory and publication contracts."""

from cadgpt_regulations.acquisition import (
    acquire_corpus,
    check_acquisition_health,
    validate_acquisition_receipt,
)
from cadgpt_regulations.catalog import load_catalog
from cadgpt_regulations.inventory import build_inventory, write_inventory
from cadgpt_regulations.validation import check_publishable, validate_manifest

__all__ = [
    "acquire_corpus",
    "build_inventory",
    "check_acquisition_health",
    "check_publishable",
    "load_catalog",
    "validate_acquisition_receipt",
    "validate_manifest",
    "write_inventory",
]
