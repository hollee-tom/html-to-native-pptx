"""Finding the font files a page loaded.

The measurer lists the page's `@font-face` rules with the absolute addresses of their sources.
The bytes come from what the browser itself fetched: every font response is kept as it arrives,
so a font service, a CDN or a local file all work as the page uses them, with no map of fonts
to maintain. A source the browser did not fetch (a face no text needed) is read from its
`file://` or `data:` address when it can be, and otherwise left out.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from playwright.sync_api import Response

from html_to_native_pptx.model import DeckFont


class FontResponses:
    """The font responses a page received, kept so their bytes can be read after it loads."""

    def __init__(self) -> None:
        """Start with nothing received."""
        self._seen: list[Response] = []

    def hear(self, response: Response) -> None:
        """Keep `response` when it is a font; pass it to `Page.on("response", ...)`."""
        if response.request.resource_type == "font":
            self._seen.append(response)

    def bodies(self) -> dict[str, bytes]:
        """Each received font's address with its bytes; a response whose body is gone is skipped."""
        found: dict[str, bytes] = {}
        for response in self._seen:
            try:
                found[response.url] = response.body()
            except Exception:  # noqa: BLE001 - a failed or redirected response has no body
                continue
        return found


def _read(source: str, fetched: dict[str, bytes]) -> bytes | None:
    """The bytes behind one font source address, or None when it cannot be read."""
    if source in fetched:
        return fetched[source]
    if source.startswith("data:"):
        head, _, payload = source.partition(",")
        try:
            return base64.b64decode(payload) if ";base64" in head else unquote(payload).encode()
        except (binascii.Error, ValueError):
            return None
    parsed = urlparse(source)
    if parsed.scheme == "file":
        path = Path(url2pathname(unquote(parsed.path)))
        return path.read_bytes() if path.is_file() else None
    return None


def deck_fonts(declared: list[dict[str, Any]], fetched: dict[str, bytes]) -> tuple[DeckFont, ...]:
    """The declared faces whose file could be read, each once.

    A face lists several sources (WOFF2, WOFF, TrueType); the browser took the first it could
    use, so the first readable one is the file the text was drawn with.
    """
    seen: set[tuple[str, int, bool, str]] = set()
    found: list[DeckFont] = []
    for face in declared:
        data = next(
            (body for source in face["sources"] if (body := _read(source, fetched)) is not None),
            None,
        )
        if data is None:
            continue
        key = (face["family"], face["weight"], face["italic"], hashlib.sha1(data).hexdigest())
        if key in seen:
            continue
        seen.add(key)
        found.append(
            DeckFont(
                family=face["family"],
                weight=face["weight"],
                weight_max=face.get("weight_max"),
                italic=face["italic"],
                data=data,
            )
        )
    return tuple(found)
