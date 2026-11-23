"""The public entry points: measure a page in Chromium and write it as a PowerPoint file."""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from html_to_native_pptx.fontfiles import FontResponses
from html_to_native_pptx.measurer import measure_deck
from html_to_native_pptx.model import MeasuredDeck
from html_to_native_pptx.pages import launch, open_page, source_url
from html_to_native_pptx.writer import deck_pptx

EXECUTABLE_ENV = "HTML_TO_NATIVE_PPTX_CHROMIUM"
"""Names a Chromium binary to use instead of the one `playwright install chromium` fetches."""


def measure(
    html: str | Path,
    *,
    slide_selector: str = "section",
    width: int = 1280,
    height: int = 720,
    embed_fonts: bool = True,
    base_dir: Path | None = None,
    freeze_animations: bool = True,
    timeout_ms: int = 60_000,
    executable_path: str | None = None,
) -> MeasuredDeck:
    """Draw a deck in Chromium and return what it measured, without writing a file.

    Useful to inspect or test the measurements; `convert` is this followed by the writer.
    Arguments are those of `convert`.
    """
    executable = executable_path or os.environ.get(EXECUTABLE_ENV)
    responses = FontResponses()
    with source_url(html, base_dir) as url, sync_playwright() as playwright:
        browser = launch(playwright, executable)
        try:
            page = open_page(
                browser,
                url,
                width,
                height,
                freeze_animations=freeze_animations,
                timeout_ms=timeout_ms,
                on_response=responses.hear,
            )
            return measure_deck(page, slide_selector, width, height, responses, fonts=embed_fonts)
        finally:
            browser.close()


def convert(
    html: str | Path,
    out: Path,
    *,
    slide_selector: str = "section",
    width: int = 1280,
    height: int = 720,
    embed_fonts: bool = True,
    base_dir: Path | None = None,
    freeze_animations: bool = True,
    timeout_ms: int = 60_000,
    executable_path: str | None = None,
) -> Path:
    """Convert a deck of HTML slides to a native, editable PowerPoint file and return its path.

    `html` is a `Path` to a file, or a string of HTML markup (then `base_dir` is where its
    relative links resolve). Every element matching `slide_selector` is one slide of
    `width` x `height` CSS pixels. With `embed_fonts` the fonts the page loaded are embedded in
    the file. `freeze_animations` jumps animations to their last frame before measuring.
    `executable_path` (or the `HTML_TO_NATIVE_PPTX_CHROMIUM` variable) names a Chromium to drive.
    """
    deck = measure(
        html,
        slide_selector=slide_selector,
        width=width,
        height=height,
        embed_fonts=embed_fonts,
        base_dir=base_dir,
        freeze_animations=freeze_animations,
        timeout_ms=timeout_ms,
        executable_path=executable_path,
    )
    out.write_bytes(deck_pptx(deck, embed_fonts=embed_fonts))
    return out
