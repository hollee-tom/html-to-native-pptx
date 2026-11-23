"""The visual check: LibreOffice draws the PPTX, and each page is compared with Chromium's
screenshot of the HTML slide as the mean absolute grey-level difference at 640x360.

LibreOffice stands in for PowerPoint. It differs in line breaking, font fallback, variable
fonts and highlight rendering, so these numbers say how close the file is to the page in one
renderer, not how it looks in PowerPoint.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = (640, 360)
DPI = 50


def render(pptx: Path, out: Path) -> int:
    """Convert `pptx` to PDF with LibreOffice and rasterise its pages to `out/pNN.png`.

    Returns the page count.
    """
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            ["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf",
             "--outdir", str(out), str(pptx)],
            check=True, capture_output=True, timeout=600,
        )
    pdf = out / f"{pptx.stem}.pdf"
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(out / "p")], check=True)
    return len(list(out.glob("p-*.png")))


def compare(shots: Path, pages: Path) -> list[float]:
    """The mean absolute grey difference of each slide's screenshot and rendered page."""
    scores = []
    for shot, page in zip(sorted(shots.glob("s*.png")), sorted(pages.glob("p-*.png")), strict=False):
        a = np.asarray(Image.open(shot).convert("L").resize(SIZE), dtype=float)
        b = np.asarray(Image.open(page).convert("L").resize(SIZE), dtype=float)
        scores.append(float(np.abs(a - b).mean()))
    return scores
