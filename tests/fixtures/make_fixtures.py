"""Generate the test IFC. Deterministic; run it to regenerate `three_doors.ifc`.

Three doors, one per status, against `door_width.ids` (minimum 900):

    wide     OverallWidth 1000  -> PASS
    narrow   OverallWidth  800  -> FAIL           a width is stated, and it is too small
    unknown  OverallWidth unset -> INDETERMINATE  no width is stated at all

That third door is the whole point of the product. `ifctester` reports it as a failure
identical in kind to the 800mm door; it is not one.

The file carries no unit assignment, so the IDS bounds compare raw numbers. Real models
differ - Schependomlaan is millimetres, the Duplex sample is metres - a real problem for
authoring portable numeric rules, but not one this fixture exists to test.

    python tests/fixtures/make_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

import ifcopenshell

OUT = Path(__file__).parent / "three_doors.ifc"

DOORS: tuple[tuple[str, str, float | None], ...] = (
    ("3worKcMPzD8x0Y1nJVBqA1", "wide", 1000.0),
    ("3worKcMPzD8x0Y1nJVBqA2", "narrow", 800.0),
    ("3worKcMPzD8x0Y1nJVBqA3", "unknown", None),
)


def build() -> None:
    model = ifcopenshell.file(schema="IFC4")
    for global_id, name, width in DOORS:
        model.create_entity("IfcDoor", GlobalId=global_id, Name=name, OverallWidth=width)
    model.write(str(OUT))


if __name__ == "__main__":
    build()
    print(f"wrote {OUT}")
