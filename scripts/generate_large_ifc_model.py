"""Grow a real IFC model past a target size by duplicating its own content.

T-0033 needs a model materially larger than the 47MB Schependomlaan fixture to measure
where peak memory goes as size grows, and no larger real-world sample was available to
fetch. Inventing geometry would violate the product's own "never invent" rule for what the
*checking engine* does, but this script produces a *test fixture*, not a finding: the
output filename must say plainly that it is generated (e.g. `Schependomlaan_large.ifc`,
never a name that reads as a fourth real sample), and the measurement table that reports on
it must caption it the same way. This script takes no `--label` or similar flag -- the
honesty is enforced by the caller naming `--output` and the table's caption honestly, not
by anything this script stamps in itself.

The method: every element directly contained in a spatial structure (a wall, door, slab,
...) is deep-copied with `ifcopenshell.util.element.copy_deep`, which regenerates each
copy's `GlobalId` and recursively copies its placement and geometric representation --
the two things that actually dominate an IFC file's bytes. Shared entities reachable from
more than one element (an `IfcOwnerHistory`, a shared material) are copied once and reused,
matching how the original model itself shares them, rather than being duplicated once per
element. The new elements are related into the model's first storey through a fresh
`IfcRelContainedInSpatialStructure`, so the result is a structurally valid IFC file
`cadgpt_engine.run_check` can open and evaluate exactly like any other.

Each `--passes` duplicates whatever is *currently* contained, including what a prior pass
already added, so passes compound: `--passes 1` doubles the contained element count,
`--passes 2` quadruples it (not triples it -- pass 2 re-scans the containment relationship
pass 1 added, so it duplicates 2x worth of elements, reaching 4x). Name the output and any
label by the actual multiple, not by the pass count.

    uv run python scripts/generate_large_ifc_model.py \\
        --source /path/to/Schependomlaan.ifc \\
        --output /path/to/Schependomlaan_large.ifc \\
        --passes 2
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.util.element as ifc_element


def _duplicate_contents_once(model: ifcopenshell.file) -> int:
    """One pass: copy every spatially-contained element and re-attach the copies.

    Returns the number of elements copied.
    """
    storeys = model.by_type("IfcBuildingStorey")
    if not storeys:
        raise SystemExit("Source model has no IfcBuildingStorey to attach copies to.")
    target_storey = storeys[0]

    containment_rels = model.by_type("IfcRelContainedInSpatialStructure")
    elements = [el for rel in containment_rels for el in rel.RelatedElements]

    owner_histories = model.by_type("IfcOwnerHistory")
    owner_history = owner_histories[0] if owner_histories else None

    copied_entities: dict[int, ifcopenshell.entity_instance] = {}
    new_elements = [
        ifc_element.copy_deep(model, element, copied_entities=copied_entities)
        for element in elements
    ]

    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=owner_history,
        Name="Duplicated content (stress test fixture -- see scripts/"
        "generate_large_ifc_model.py)",
        RelatedElements=new_elements,
        RelatingStructure=target_storey,
    )
    return len(new_elements)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="a real IFC file")
    parser.add_argument("--output", type=Path, required=True, help="where to write it")
    parser.add_argument(
        "--passes",
        type=int,
        default=1,
        help="how many times to duplicate the model's own contained elements (default 1)",
    )
    args = parser.parse_args(argv)

    t0 = time.monotonic()
    model = ifcopenshell.open(args.source)
    print(
        f"opened {args.source} ({args.source.stat().st_size:,} bytes) "
        f"in {time.monotonic() - t0:.1f}s",
        file=sys.stderr,
    )

    for i in range(args.passes):
        t0 = time.monotonic()
        n = _duplicate_contents_once(model)
        print(
            f"pass {i + 1}/{args.passes}: duplicated {n} elements "
            f"in {time.monotonic() - t0:.1f}s",
            file=sys.stderr,
        )

    t0 = time.monotonic()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(args.output))
    size = args.output.stat().st_size
    print(
        f"wrote {args.output} ({size:,} bytes) in {time.monotonic() - t0:.1f}s",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
