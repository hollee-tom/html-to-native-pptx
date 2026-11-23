"""Colour and opacity as DrawingML writes them.

PowerPoint has no group opacity, so the measurer folds every element's and ancestor's
`opacity` into each colour's alpha; this module is where that alpha becomes `<a:alpha>`.
"""

from lxml import etree
from pptx.dml.color import ColorFormat, RGBColor
from pptx.oxml.ns import qn


def rgb(colour: str) -> RGBColor:
    """A `#rrggbb` colour as python-pptx takes it."""
    return RGBColor.from_string(colour.lstrip("#")[:6].upper())


def paint(target: ColorFormat, colour: str) -> None:
    """Set a fill, line or text colour. A `#rrggbbaa` colour is see-through: its alpha is
    written as PowerPoint's own, so a tint over a slide or a photo stays a tint.
    """
    target.rgb = rgb(colour)
    alpha = alpha_of(colour)
    if alpha is None:
        return
    shade = target._color._xClr  # python-pptx has no alpha setter
    for old in shade.findall(qn("a:alpha")):
        shade.remove(old)
    etree.SubElement(shade, qn("a:alpha")).set("val", alpha)


def alpha_of(colour: str) -> str | None:
    """A `#rrggbbaa` colour's opacity as DrawingML writes it, or None when it is solid."""
    digits = colour.lstrip("#")
    return str(round(int(digits[6:8], 16) / 255 * 100_000)) if len(digits) == 8 else None
