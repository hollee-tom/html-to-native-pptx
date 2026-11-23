"""Run the benchmark: convert the corpus with each tool, score every file, write the results.

    python benchmark/run.py --tools nativedeck,dom-to-pptx

Everything here needs Chromium, LibreOffice and poppler; `benchmark/run.sh` runs it in the
project's Docker image so anyone gets the same renderer.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ground  # noqa: E402
import lofonts  # noqa: E402
import score  # noqa: E402
import visual  # noqa: E402

TOOLS = {
    "nativedeck": lambda html, out, sel, w, h: [
        sys.executable,
        "-m",
        "nativedeck",
        str(html),
        "-o",
        str(out),
        "-s",
        sel,
        "--width",
        str(w),
        "--height",
        str(h),
    ],
    "dom-to-pptx": lambda html, out, sel, w, h: [
        sys.executable,
        str(HERE / "adapters/dom_to_pptx.py"),
        str(html),
        str(out),
        sel,
        str(w),
        str(h),
    ],
}


def run_tool(
    name: str, args: argparse.Namespace, shots: Path, ground_truth: list[dict[str, Any]]
) -> dict[str, Any]:
    """Convert with one tool and score its file; a tool that fails is reported, not fatal."""
    out = args.out / name
    out.mkdir(parents=True, exist_ok=True)
    pptx = out / "deck.pptx"
    started = time.time()
    done = subprocess.run(
        TOOLS[name](args.html, pptx, args.selector, args.width, args.height),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    seconds = round(time.time() - started, 1)
    if done.returncode != 0 or not pptx.exists():
        return {
            "error": done.stderr.strip()[-400:] or "no file written",
            "convert_seconds": seconds,
        }
    result: dict[str, Any] = {"convert_seconds": seconds, "bytes": pptx.stat().st_size}
    result.update(score.structure(pptx, ground_truth, args.width))
    result["features"] = score.features(pptx, ground_truth, args.width)
    pages = out / "pages"
    result["libreoffice_pages"] = visual.render(pptx, pages)
    maes = visual.compare(shots, pages)
    result["pixel_mae_mean"] = round(sum(maes) / len(maes), 2)
    result["pixel_mae_per_slide"] = [round(m, 1) for m in maes]
    result["pixel_mae_slides_over_15"] = sum(m > 15 for m in maes)
    return result


def table(results: dict[str, Any], slides: int) -> str:
    """The results as a Markdown table, one column per tool."""
    names = [n for n, r in results.items() if "error" not in r]
    rows = [
        (
            "Slides written / LibreOffice pages",
            lambda r: f"{r['slides']} / {r['libreoffice_pages']} (of {slides})",
        ),
        (
            "Letters and digits missing / extra",
            lambda r: (
                f"{r['characters_missing']} / {r['characters_extra']} of {r['characters_expected']}"
            ),
        ),
        (
            "Text centre distance from its box, median / p90 (px)",
            lambda r: f"{r['text_centre_distance_median_px']} / {r['text_centre_distance_p90_px']}",
        ),
        (
            "Text blocks outside their box",
            lambda r: f"{r['text_blocks_outside_source_box']} of {r['text_blocks_checked']}",
        ),
        ("Native text boxes", lambda r: r["native_text_boxes"]),
        ("Native shapes", lambda r: r["native_shapes"]),
        ("Native tables", lambda r: r["native_tables"]),
        ("Native charts", lambda r: r["native_charts"]),
        ("Pictures", lambda r: r["pictures"]),
        ("Embedded font parts", lambda r: r["embedded_font_parts"]),
        ("Pixel MAE mean (lower is better)", lambda r: r["pixel_mae_mean"]),
        ("Slides with MAE over 15", lambda r: r["pixel_mae_slides_over_15"]),
        ("Convert time (s)", lambda r: r["convert_seconds"]),
    ]
    kinds = sorted({k for n in names for k in results[n]["features"]})
    lines = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for label, get in rows:
        lines.append(f"| {label} | " + " | ".join(str(get(results[n])) for n in names) + " |")
    for kind in kinds:
        cells = []
        for n in names:
            passed, total = results[n]["features"].get(kind, [0, 0])
            cells.append(f"{passed}/{total}")
        lines.append(f"| feature: {kind} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    """Parse the arguments and run every requested tool."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, default=HERE.parent / "corpus/deck.html")
    parser.add_argument("--fonts", type=Path, default=HERE.parent / "corpus/fonts")
    parser.add_argument("--out", type=Path, default=HERE / "out")
    parser.add_argument("--selector", default="section")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--tools", default="nativedeck")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    lofonts.install(args.fonts, Path.home() / ".fonts")
    truth, slides = ground.record(args.html, args.out, args.selector, args.width, args.height)
    results = {
        name: run_tool(name, args, args.out / "shots", truth) for name in args.tools.split(",")
    }
    document = {"corpus": {"html": args.html.name, "slides": slides}, "results": results}
    (args.out / "results.json").write_text(json.dumps(document, indent=1))
    (args.out / "results.md").write_text(table(results, slides) + "\n")
    print(table(results, slides))
    for name, result in results.items():
        if "error" in result:
            print(f"{name} failed: {result['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
