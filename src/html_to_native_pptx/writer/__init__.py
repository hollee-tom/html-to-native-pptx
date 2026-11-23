"""Writes a measured deck as a PowerPoint file made of objects a person can edit.

Every part of a slide that PowerPoint has an object for becomes that object, at the position
and size the browser measured: text becomes text boxes with their fonts, colours and bullets,
tables become tables with their merged cells, charts become PowerPoint charts with their
numbers, and plain shapes become shapes. Only what PowerPoint cannot represent, such as a
drawing or a gradient, arrives as a picture of just that part.

It uses python-pptx, which writes the file format directly, so no browser or Office is needed
here: the drawing is done before, in `html_to_native_pptx.browser`.
"""

import io

from pptx import Presentation
from pptx.slide import Slide

from html_to_native_pptx.fonts import Typefaces
from html_to_native_pptx.model import (
    ChartItem,
    MeasuredDeck,
    MeasuredSlide,
    PictureItem,
    TableItem,
    TextItem,
)
from html_to_native_pptx.writer.charts import add_chart
from html_to_native_pptx.writer.colour import paint
from html_to_native_pptx.writer.pictures import add_picture
from html_to_native_pptx.writer.shapes import add_shape
from html_to_native_pptx.writer.tables import add_table
from html_to_native_pptx.writer.text import add_text
from html_to_native_pptx.writer.units import emu

BLANK_LAYOUT = 6
"""Index of python-pptx's blank layout, so no placeholder boxes appear on a slide."""


def deck_pptx(deck: MeasuredDeck, *, embed_fonts: bool = True) -> bytes:
    """The PowerPoint file for a measured deck, one slide per measured slide at its canvas size.

    With `embed_fonts`, every font file the deck's runs were drawn with is put inside the file
    (unless its licence forbids embedding), so the deck looks the same where the font is not
    installed.
    """
    presentation = Presentation()
    presentation.slide_width = emu(deck.width)
    presentation.slide_height = emu(deck.height)
    layout = presentation.slide_layouts[BLANK_LAYOUT]
    faces = Typefaces.of(deck.fonts if embed_fonts else ())
    for measured in deck.slides:
        _slide(presentation.slides.add_slide(layout), measured, deck, faces)
    written = io.BytesIO()
    presentation.save(written)
    return faces.embedded(written.getvalue())


def _slide(slide: Slide, measured: MeasuredSlide, deck: MeasuredDeck, faces: Typefaces) -> None:
    """Fill one slide: its background, then every item from back to front."""
    if measured.background is not None:
        slide.background.fill.solid()
        paint(slide.background.fill.fore_color, measured.background)
    if measured.picture is not None:
        slide.shapes.add_picture(
            io.BytesIO(measured.picture), 0, 0, emu(deck.width), emu(deck.height)
        )
    for item in measured.items:
        if isinstance(item, TextItem):
            add_text(slide.shapes, item, faces)
        elif isinstance(item, TableItem):
            add_table(slide.shapes, item, faces)
        elif isinstance(item, ChartItem):
            if item.categories and any(series.values for series in item.series):
                add_chart(slide.shapes, item)
        elif isinstance(item, PictureItem):
            add_picture(slide.shapes, item)
        else:
            add_shape(slide.shapes, item)
