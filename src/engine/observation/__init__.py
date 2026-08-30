"""``engine.observation`` — the shared kernel: property names and their conventions.

Public surface documented in ``readme.ai.md`` beside this file.
"""

from __future__ import annotations

from engine.observation.property_name import (
    CONVENTION_FREE_BASES,
    CONVENTIONS,
    ConventionMissing,
    PropertyName,
    UnknownConvention,
)

__all__ = [
    "CONVENTIONS",
    "CONVENTION_FREE_BASES",
    "ConventionMissing",
    "PropertyName",
    "UnknownConvention",
]
