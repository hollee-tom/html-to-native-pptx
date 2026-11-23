"""The `html-to-native-pptx` command: `html-to-native-pptx deck.html -o deck.pptx`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from html_to_native_pptx import __version__
from html_to_native_pptx.convert import convert
from html_to_native_pptx.errors import ConversionError


def parser() -> argparse.ArgumentParser:
    """The command's arguments."""
    found = argparse.ArgumentParser(
        prog="html-to-native-pptx", description="High-fidelity HTML to native, editable PowerPoint."
    )
    found.add_argument("html", type=Path, help="the HTML file holding the slides")
    found.add_argument(
        "-o", "--out", type=Path, help="the .pptx to write (default: beside the input)"
    )
    found.add_argument(
        "-s",
        "--slide-selector",
        default="section",
        help="CSS selector of one slide (default: section)",
    )
    found.add_argument(
        "--width", type=int, default=1280, help="slide width in CSS pixels (default: 1280)"
    )
    found.add_argument(
        "--height", type=int, default=720, help="slide height in CSS pixels (default: 720)"
    )
    found.add_argument(
        "--no-embed-fonts", action="store_true", help="name fonts only; do not embed them"
    )
    found.add_argument(
        "--no-freeze-animations", action="store_true", help="measure animations as they stand"
    )
    found.add_argument("--chromium", help="path of a Chromium binary to drive")
    found.add_argument(
        "--timeout", type=int, default=60, help="seconds to wait on the page (default: 60)"
    )
    found.add_argument("--version", action="version", version=f"html-to-native-pptx {__version__}")
    return found


def main(argv: list[str] | None = None) -> int:
    """Run the command; returns the exit status."""
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="html-to-native-pptx: %(message)s")
    out = args.out or args.html.with_suffix(".pptx")
    try:
        convert(
            args.html,
            out,
            slide_selector=args.slide_selector,
            width=args.width,
            height=args.height,
            embed_fonts=not args.no_embed_fonts,
            freeze_animations=not args.no_freeze_animations,
            timeout_ms=args.timeout * 1000,
            executable_path=args.chromium,
        )
    except ConversionError as error:
        print(f"html-to-native-pptx: {error}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
