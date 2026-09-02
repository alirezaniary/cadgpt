"""Typed failures, so a caller can tell a bad upload from a broken engine.

Without these the API layer would catch `Exception` around the inherited libraries and
could not distinguish "this user sent a malformed IDS" (a 4xx, the user's problem, worth
an actionable message) from "the engine broke" (a 5xx, ours). CLAUDE.md forbids swallowing
an exception to make output clean; naming them is how that rule is kept while still
returning a useful response.
"""

from __future__ import annotations


class EngineError(Exception):
    """Base class for every failure this package raises deliberately."""


class InvalidInputError(EngineError):
    """The caller supplied a file the engine cannot work with."""


class InvalidIdsError(InvalidInputError):
    """The IDS file is not valid against the buildingSMART IDS schema.

    Raised rather than evaluated-anyway on purpose: a malformed rule set that is partly
    parsed produces a report that under-checks the model while looking complete.
    """


class InvalidIfcError(InvalidInputError):
    """The IFC file could not be parsed by ifcopenshell."""
