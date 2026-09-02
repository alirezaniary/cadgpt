"""Run a check from a terminal, over real files, and print the result.

This exists so the engine can be exercised at a real entry point without a database, a
queue, or a browser in the way. `make verify` proves the types and the tests; this proves
the thing actually runs.

    cadgpt-check model.ifc rules.ids
    cadgpt-check model.ifc rules.ids --json > report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cadgpt_engine.check import run_check
from cadgpt_engine.errors import InvalidInputError
from cadgpt_engine.messages import default_message
from cadgpt_engine.report import Report
from cadgpt_engine.status import Status


def _summarize(report: Report) -> str:
    lines = [
        f"{report.ifc_filename} ({report.ifc_schema})  against  {report.ids_title!r}",
        f"engine {report.engine_version}",
        "",
        f"  overall            {report.status.value}",
        f"  specifications     {report.specifications_passed} pass / "
        f"{report.specifications_failed} fail / "
        f"{report.specifications_indeterminate} indeterminate",
        f"  entity outcomes    {report.passed} pass / {report.failed} fail / "
        f"{report.indeterminate} indeterminate",
        "",
    ]
    for spec in report.specifications:
        lines.append(f"  [{spec.status.value:>13}] {spec.name or '(unnamed)'}")
        lines.append(
            f"      {spec.applicability.value}, cardinality {spec.cardinality}, "
            f"{spec.matched} element(s) matched"
        )
        if spec.reason_code is not None:
            lines.append(f"      {default_message(spec.reason_code)}")
        for req in spec.requirements:
            for entity in req.entities:
                if entity.status is Status.PASS:
                    continue
                lines.append(
                    f"      - {entity.status.value:<13} {entity.ifc_class} "
                    f"{entity.global_id}  {entity.reason_code.value}: {entity.detail}"
                )
            if req.entities_omitted:
                lines.append(
                    f"      ... {req.entities_omitted} further non-passing element(s) "
                    "counted but not listed"
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cadgpt-check",
        description="Check an IFC model against an IDS rule set.",
    )
    parser.add_argument("ifc", type=Path, help="path to the IFC model")
    parser.add_argument("ids", type=Path, help="path to the IDS rule set")
    parser.add_argument(
        "--json", action="store_true", help="emit the canonical report document"
    )
    args = parser.parse_args(argv)

    try:
        report = run_check(args.ifc, args.ids)
    except InvalidInputError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(_summarize(report))

    # A non-zero exit for anything short of a clean pass, so this composes in a pipeline.
    return 0 if report.status is Status.PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
