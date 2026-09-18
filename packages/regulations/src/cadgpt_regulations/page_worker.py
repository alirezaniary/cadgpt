"""Internal crash boundary for native PDF parsing and deterministic rendering."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cadgpt_regulations.errors import RegulationsError
from cadgpt_regulations.jsonio import canonical_bytes
from cadgpt_regulations.page_tools import PageSource
from cadgpt_regulations.storage import install_immutable_bytes, validate_output_root

_MIN_NATIVE_NONSPACE_CHARS = 20
_MIXED_BITMAP_COVERAGE_PERMYRIAD = 1_000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cadgpt-regulations-page-worker")
    subcommands = parser.add_subparsers(dest="command", required=True)
    probe = subcommands.add_parser("probe")
    probe.add_argument("--source", type=Path, required=True)
    probe.add_argument("--page", type=int, required=True)
    probe.add_argument("--page-id", required=True)
    probe.add_argument("--dpi", type=int, required=True)
    probe.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_output_root(args.output, description="page worker output")
        with PageSource(args.source) as source:
            native = source.native_page(args.page, page_id=args.page_id)
            raw_text = str(native["raw_glyph_text"])
            bitmap_coverage = int(native["bitmap_coverage_permyriad"])
            render_needed = (
                sum(not character.isspace() for character in raw_text)
                < _MIN_NATIVE_NONSPACE_CHARS
                or bitmap_coverage >= _MIXED_BITMAP_COVERAGE_PERMYRIAD
            )
            if render_needed:
                render, render_metrics = source.render_png(args.page, dpi=args.dpi)
            else:
                render, render_metrics = None, None
        install_immutable_bytes(args.output / "native.json", canonical_bytes(native))
        if render is not None:
            install_immutable_bytes(args.output / "render.png", render)
        install_immutable_bytes(
            args.output / "result.json",
            canonical_bytes({"render_metrics": render_metrics}),
        )
        return 0
    except RegulationsError as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
