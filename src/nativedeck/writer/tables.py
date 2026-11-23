"""Native tables with their merged cells, fills and borders.

A cell writes only the sides the page borders; every bare side is written as an explicit no
line and the table uses PowerPoint's "No Style, No Grid" style. Without both, the default table
style drew the unbordered sides as a black grid.
"""

from lxml import etree
from pptx.oxml.ns import qn
from pptx.shapes.shapetree import SlideShapes
from pptx.table import _Cell

from nativedeck.fonts import Typefaces
from nativedeck.model import Border, Cell, Insets, TableItem
from nativedeck.writer.colour import alpha_of, paint
from nativedeck.writer.text import ANCHORS, write_paragraphs
from nativedeck.writer.units import emu, place

NO_GRID = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
"""PowerPoint's built-in "No Style, No Grid" table style."""


BORDER_TAGS = (("left", "a:lnL"), ("right", "a:lnR"), ("top", "a:lnT"), ("bottom", "a:lnB"))


def add_table(shapes: SlideShapes, item: TableItem, faces: Typefaces) -> None:
    """Add a native table with the measured column widths, row heights, merges, fills and
    borders, and none of PowerPoint's own table styling.
    """
    frame = shapes.add_table(len(item.rows), len(item.columns), *place(item.box))
    table = frame.table
    table.first_row = False
    table.horz_banding = False
    # "No Style, No Grid": a side the page leaves bare stays bare, not the default style's grid.
    styled = table._tbl.tblPr.find(qn("a:tableStyleId"))
    if styled is None:
        styled = etree.SubElement(table._tbl.tblPr, qn("a:tableStyleId"))
    styled.text = NO_GRID
    for at, width in enumerate(item.columns):
        table.columns[at].width = emu(width)
    for at, height in enumerate(item.rows):
        table.rows[at].height = emu(height)
    for row in range(len(item.rows)):
        for column in range(len(item.columns)):
            table.cell(row, column).fill.background()
    for cell in item.cells:
        if cell.row >= len(item.rows) or cell.column >= len(item.columns):
            continue
        written = table.cell(cell.row, cell.column)
        last_row = min(cell.row + cell.rowspan, len(item.rows)) - 1
        last_column = min(cell.column + cell.colspan, len(item.columns)) - 1
        if (last_row, last_column) != (cell.row, cell.column):
            written.merge(table.cell(last_row, last_column))
        _cell(written, cell, faces)


def _cell(written: _Cell, cell: Cell, faces: Typefaces) -> None:
    """Write one cell's text, fill, insets and borders."""
    if cell.fill is not None:
        written.fill.solid()
        paint(written.fill.fore_color, cell.fill)
    written.vertical_anchor = ANCHORS[cell.vertical]
    write_paragraphs(written.text_frame, cell.paragraphs, Insets(), faces)
    written.margin_left = emu(cell.insets.left)
    written.margin_top = emu(cell.insets.top)
    written.margin_right = emu(cell.insets.right)
    written.margin_bottom = emu(cell.insets.bottom)
    properties = written._tc.get_or_add_tcPr()
    for at, (side, tag) in enumerate(BORDER_TAGS):
        border = getattr(cell, side)
        properties.insert(
            at,
            _line(tag, border.width, border.colour)
            if isinstance(border, Border)
            else _no_line(tag),
        )


def _no_line(tag: str) -> etree._Element:
    """A cell side drawn with no line, so no table style can give it one."""
    line = etree.Element(qn(tag))
    line.set("w", "0")
    etree.SubElement(line, qn("a:noFill"))
    return line


def _line(tag: str, width: float, colour: str) -> etree._Element:
    """A DrawingML line of a width in pixels and a colour."""
    line = etree.Element(qn(tag))
    line.set("w", str(int(emu(width))))
    fill = etree.SubElement(line, qn("a:solidFill"))
    shade = etree.SubElement(fill, qn("a:srgbClr"))
    shade.set("val", colour.lstrip("#")[:6].upper())
    if (alpha := alpha_of(colour)) is not None:
        etree.SubElement(shade, qn("a:alpha")).set("val", alpha)
    return line
