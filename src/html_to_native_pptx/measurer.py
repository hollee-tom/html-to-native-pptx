"""Measuring a page in Chromium: the slides' layout, and a transparent picture of each part
PowerPoint has no object for.

The measuring script (`assets/measure.js`) walks each slide's DOM and reports text with runs,
tables, charts, shapes and the elements to be pictured. Each of those is then screenshot on
its own, with everything else hidden, so the picture holds just that element over a
transparent background.
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from typing import Any

from playwright.sync_api import Page
from pydantic import TypeAdapter, ValidationError

from html_to_native_pptx.errors import ConversionError
from html_to_native_pptx.fontfiles import FontResponses, deck_fonts
from html_to_native_pptx.model import Item, MeasuredDeck, MeasuredSlide, PictureItem

logger = logging.getLogger(__name__)

MARK = "data-html-to-native-pptx"
ISOLATED = "html-to-native-pptx-isolated"
PICTURE_MS = 10_000
WHOLE = (
    "html, body { background: transparent !important; } "
    "body * { visibility: hidden !important; } "
    '[MARK="ID"], [MARK="ID"] * { visibility: visible !important; }'
)
"""Pictures an element and everything inside it, as an `<img>`, an `<svg>` or a shape with a
background image is drawn."""
BACKGROUND = (
    "html, body { background: transparent !important; } "
    "body * { visibility: hidden !important; } "
    '[MARK="ID"] { visibility: visible !important; -webkit-text-fill-color: transparent '
    "!important; text-shadow: none !important; text-decoration-color: transparent !important; } "
    '[MARK="ID"]::before, [MARK="ID"]::after { -webkit-text-fill-color: currentColor !important; }'
)
"""Pictures only an element's own background, gradient and `::before`/`::after`, with its text
made clear: the text stays native and editable, placed over this picture."""
SLIDE_TOLERANCE = 2.0
"""How far, in pixels, a slide may differ from the canvas before a warning is logged."""

_ITEMS: TypeAdapter[Item] = TypeAdapter(Item)


def _script() -> str:
    """The measuring script's source."""
    return resources.files("html_to_native_pptx").joinpath("assets/measure.js").read_text("utf-8")


def _picture(page: Page, mode: str, identifier: str) -> bytes | None:
    """A transparent screenshot of the element marked `identifier`, or None if it cannot be taken.

    The rule that hides everything else is added for this one shot and removed after, so each
    picture holds just its own element.
    """
    rule = (
        (WHOLE if mode == "whole" else BACKGROUND).replace("MARK", MARK).replace("ID", identifier)
    )
    page.add_style_tag(content=rule)
    page.evaluate(
        "(name) => { const all = document.querySelectorAll('style'); "
        "all[all.length - 1].id = name; }",
        ISOLATED,
    )
    try:
        return page.locator(f'[{MARK}="{identifier}"]').screenshot(
            omit_background=True, animations="disabled", timeout=PICTURE_MS
        )
    except Exception as error:  # noqa: BLE001 - a part that cannot be pictured is left out
        logger.warning("picture %s not taken: %s", identifier, type(error).__name__)
        return None
    finally:
        page.evaluate(f"document.getElementById('{ISOLATED}').remove()")


def measure_deck(
    page: Page, selector: str, width: int, height: int, responses: FontResponses, *, fonts: bool
) -> MeasuredDeck:
    """Measure every slide `selector` matches on a loaded `page`.

    Raises `ConversionError` when nothing matches. With `fonts`, the font files the page loaded
    are returned with the deck so the writer can embed them.
    """
    found = page.evaluate(_script(), selector)
    measured: dict[str, Any] = json.loads(found) if isinstance(found, str) else found
    if not measured["slides"]:
        raise ConversionError(f"no element matches the slide selector {selector!r}")
    pictures: dict[str, bytes] = {}
    for picture in measured["pictures"]:
        shot = _picture(page, picture["mode"], picture["id"])
        if shot is not None:
            pictures[picture["id"]] = shot
    boxes = {picture["id"]: picture["box"] for picture in measured["pictures"]}
    slides: list[MeasuredSlide] = []
    for number, slide in enumerate(measured["slides"], start=1):
        size = slide["size"]
        if (
            abs(size["width"] - width) > SLIDE_TOLERANCE
            or abs(size["height"] - height) > SLIDE_TOLERANCE
        ):
            logger.warning(
                "slide %d is %.0fx%.0f, not the %dx%d canvas",
                number,
                size["width"],
                size["height"],
                width,
                height,
            )
        items: list[Item] = []
        for item in slide["items"]:
            if item.get("kind") != "picture":
                items.append(_ITEMS.validate_python(item))
            elif (shot := pictures.get(str(item["id"]))) is not None:
                items.append(PictureItem(box=boxes[str(item["id"])], png=shot))
        marked = slide.get("picture")
        try:
            slides.append(
                MeasuredSlide(
                    background=slide.get("background"),
                    picture=pictures.get(marked) if isinstance(marked, str) else None,
                    items=tuple(items),
                )
            )
        except ValidationError as error:
            raise ConversionError(f"slide {number} was measured malformed: {error}") from None
    carried = deck_fonts(measured["fonts"], responses.bodies()) if fonts else ()
    return MeasuredDeck(width=width, height=height, slides=tuple(slides), fonts=carried)
