"""Opening the page: where the HTML comes from, and how the browser is driven to see it ready.

The page is loaded as any browser loads it: its scripts run, its stylesheets and images load
from wherever they point, and its fonts load as it asks for them. Nothing is rewritten, because
text measured in a fallback font measures wrongly.
"""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Browser, Page, Playwright, Response

FROZEN = (
    "*, *::before, *::after { animation-duration: 0s !important; animation-delay: 0s !important; "
    "animation-iteration-count: 1 !important; animation-fill-mode: both !important; "
    "transition: none !important; scroll-behavior: auto !important; }"
)
"""Every animation jumps to its last frame and stays there, so a slide that fades its content in
is measured as the audience eventually sees it, and the pictures are not taken mid-motion."""
SETTLE_MS = 3_000
"""How long the page is given to go quiet on the network after it has loaded; a page that never
does, such as one holding a connection open, is measured anyway."""


@contextmanager
def source_url(source: str | Path, base_dir: Path | None) -> Iterator[str]:
    """The address to load for `source`.

    A `Path` is a file and is loaded where it is, so its relative links work. A string is HTML
    markup; it is written to a temporary file (in `base_dir`, when given, so its relative links
    work) because a page loaded from nowhere may not read local files.
    """
    if isinstance(source, Path):
        yield source.resolve().as_uri()
        return
    folder = base_dir.resolve() if base_dir is not None else None
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", prefix=".nativedeck-", dir=folder, delete=False, encoding="utf-8"
    ) as written:
        written.write(source)
    path = Path(written.name)
    try:
        yield path.as_uri()
    finally:
        path.unlink(missing_ok=True)


def launch(playwright: Playwright, executable_path: str | None) -> Browser:
    """Chromium, headless; `executable_path` names a browser to use instead of Playwright's."""
    return playwright.chromium.launch(executable_path=executable_path)


def open_page(
    browser: Browser,
    url: str,
    width: int,
    height: int,
    *,
    freeze_animations: bool,
    timeout_ms: int,
    on_response: Callable[[Response], None],
) -> Page:
    """A page at the canvas size with `url` loaded, its fonts ready and its animations settled.

    `on_response` hears every response from the first request on, so no font file is missed.
    """
    page = browser.new_page(viewport={"width": width, "height": height})
    page.on("response", on_response)
    page.set_default_timeout(timeout_ms)
    page.emulate_media(media="screen")
    page.goto(url, wait_until="load")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
    if freeze_animations:
        page.add_style_tag(content=FROZEN)
    page.evaluate("document.fonts.ready.then(() => true)")
    return page
