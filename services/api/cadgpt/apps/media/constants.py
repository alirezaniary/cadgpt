from __future__ import annotations

from cadgpt.apps.media.choices import MediaKind

#: Accepted extensions per kind. A file is identified by extension and by parsing it
#: later; the browser-supplied content type is not trusted for anything.
ALLOWED_EXTENSIONS: dict[str, frozenset[str]] = {
    MediaKind.IFC_MODEL: frozenset({".ifc", ".ifcxml", ".ifczip"}),
    MediaKind.IDS_RULESET: frozenset({".ids", ".xml"}),
    MediaKind.REPORT: frozenset({".md"}),
}

#: An IDS rule set is a small XML document. A megabyte is already far past generous, and
#: the cap stops a rule-set upload being used as a way around the model size limit.
#: A generated report is text rendered from a stored JSON document already bounded by
#: `CHECK_ENTITY_LIMIT` -- the same order of magnitude as an IDS file, not a model.
MAX_BYTES: dict[str, int] = {
    MediaKind.IDS_RULESET: 8 * 1024 * 1024,
    MediaKind.REPORT: 8 * 1024 * 1024,
}

#: Read size when checksumming. Large enough to be fast, small enough that a 500MB model
#: never sits in memory.
CHECKSUM_CHUNK_BYTES = 1024 * 1024
