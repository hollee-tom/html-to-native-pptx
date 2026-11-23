"""Plain shapes: rectangles, rounded rectangles, ellipses and lines.

python-pptx gives every shape the theme's style, which points at a theme shadow; a viewer that
draws it darkens a see-through overlay on a photo by about 20 grey levels. Shapes here set their
own fill and line, so the style is removed.
"""

from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.shapes.autoshape import Shape
from pptx.shapes.shapetree import SlideShapes

from html_to_native_pptx.model import Box, ShapeItem
from html_to_native_pptx.writer.colour import paint
from html_to_native_pptx.writer.units import emu, place


def add_shape(shapes: SlideShapes, item: ShapeItem) -> None:
    """Add a rectangle, rounded rectangle, ellipse or line with its fill and outline."""
    if item.shape == "line":
        left, top, width, height = place(item.box)
        connector = shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT, left, top + height // 2, left + width, top + height // 2
        )
        connector.line.width = emu(max(item.line_width, item.box.height, 1))
        if item.line or item.fill:
            paint(connector.line.color, item.line or item.fill or "#000000")
        return
    shape = outlined(
        shapes,
        item.box,
        item.fill,
        item.line,
        item.line_width,
        item.radius,
        ellipse=item.shape == "ellipse",
    )
    if item.rotation:
        shape.rotation = item.rotation


def outlined(
    shapes: SlideShapes,
    box: Box,
    fill: str | None,
    line: str | None,
    line_width: float,
    radius: float,
    ellipse: bool = False,
) -> Shape:
    """Add a rectangle, rounded rectangle or ellipse with a fill and outline, and no shadow or
    text of PowerPoint's own.
    """
    kind = MSO_SHAPE.OVAL if ellipse else MSO_SHAPE.RECTANGLE
    if not ellipse and radius > 0:
        kind = MSO_SHAPE.ROUNDED_RECTANGLE
    shape = shapes.add_shape(kind, *place(box))
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        shape.adjustments[0] = min(0.5, radius / max(1.0, min(box.width, box.height)))
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        paint(shape.fill.fore_color, fill)
    if line is None or line_width <= 0:
        shape.line.fill.background()
    else:
        paint(shape.line.color, line)
        shape.line.width = emu(line_width)
    shape.shadow.inherit = False
    # The theme style python-pptx gives a shape points at the theme's shadow and colours; a
    # shape here sets its own, and a viewer that draws the style shadow darkens a see-through
    # fill over a photo.
    styled = shape._element.find(qn("p:style"))
    if styled is not None:
        shape._element.remove(styled)
    shape.text_frame.text = ""
    return shape
