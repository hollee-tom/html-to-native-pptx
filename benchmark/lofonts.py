"""Fonts for the LibreOffice renderer.

Every tool's file is drawn by the same LibreOffice with the same installed fonts, so a tool is
not marked down for the renderer lacking a font. Static files are installed as they are. A
variable file is cut into fixed weights named as PowerPoint names them ("Inter", "Inter Light",
"Inter SemiBold"), because LibreOffice draws a variable font at its default weight only.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from html_to_native_pptx.fonts import WEIGHT_NAMES, renamed

WEIGHTS = (300, 400, 500, 600, 700, 800)


def install(fonts: Path, target: Path) -> None:
    """Put the font files of `fonts` where fontconfig finds them, and refresh its cache."""
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(fonts.glob("*.ttf")):
        font = TTFont(path)
        if "fvar" not in font:
            (target / path.name).write_bytes(path.read_bytes())
            continue
        family = font["name"].getDebugName(16) or font["name"].getDebugName(1)
        axes = {a.axisTag: a for a in font["fvar"].axes}
        for weight in WEIGHTS:
            cut = instancer.instantiateVariableFont(
                TTFont(path), {**{t: a.defaultValue for t, a in axes.items()}, "wght": weight}
            )
            name = family if weight in (400, 700) else f"{family} {WEIGHT_NAMES[weight]}"
            renamed(cut, name, weight, weight == 700, False)
            cut.save(target / f"{family}-{weight}.ttf")
    subprocess.run(["fc-cache", "-f"], check=True, capture_output=True)
