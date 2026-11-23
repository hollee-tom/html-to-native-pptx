"""Text boxes: paragraphs, runs, bullets and what a run adds to its font.

A block with rounded corners or an outline becomes a shape holding its text, so the corners
and outline are kept. Inline backgrounds such as chips and marked words are the run's own
highlight, so the paragraph stays whole and a status chip inside a table cell keeps its fill.
"""

from collections.abc import Sequence

from lxml import etree
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.shapes.shapetree import SlideShapes
from pptx.text.text import TextFrame, _Run
from pptx.util import Pt

from nativedeck.fonts import Typefaces
from nativedeck.model import Insets, Paragraph, Run, TextItem
from nativedeck.writer.colour import alpha_of, paint
from nativedeck.writer.shapes import outlined
from nativedeck.writer.units import POINTS_PER_PIXEL, emu, place


def add_text(shapes: SlideShapes, item: TextItem, faces: Typefaces) -> None:
    """Add a text box with the block's paragraphs and insets; a block with rounded corners or
    an outline becomes a shape holding its text, so the corners and outline are kept.
    """
    if item.radius > 0 or (item.line is not None and item.line_width > 0):
        box = outlined(shapes, item.box, item.fill, item.line, item.line_width, item.radius)
    else:
        box = shapes.add_textbox(*place(item.box))
        if item.fill is not None:
            box.fill.solid()
            paint(box.fill.fore_color, item.fill)
    if item.rotation:
        box.rotation = item.rotation
    frame = box.text_frame
    frame.vertical_anchor = ANCHORS[item.vertical]
    write_paragraphs(frame, item.paragraphs, item.insets, faces)
    frame.word_wrap = item.wrap


def write_paragraphs(
    frame: TextFrame, paragraphs: Sequence[Paragraph], insets: Insets, faces: Typefaces
) -> None:
    """Write paragraphs into a text frame that wraps at its width and never resizes."""
    frame.word_wrap = True
    frame.auto_size = None
    frame.margin_left = emu(insets.left)
    frame.margin_top = emu(insets.top)
    frame.margin_right = emu(insets.right)
    frame.margin_bottom = emu(insets.bottom)
    for at, paragraph in enumerate(paragraphs or (Paragraph(),)):
        written = frame.paragraphs[0] if at == 0 else frame.add_paragraph()
        written.alignment = ALIGNS[paragraph.align]
        written.level = min(paragraph.level, 8)
        if paragraph.line_height is not None:
            written.line_spacing = Pt(paragraph.line_height * POINTS_PER_PIXEL)
        if paragraph.space_before:
            written.space_before = Pt(paragraph.space_before * POINTS_PER_PIXEL)
        if paragraph.bullet is not None:
            _bullet(written._p, paragraph)
        for run in paragraph.runs:
            if run.text == "\n":
                written.add_line_break()
                continue
            _run(written.add_run(), run, faces)


def _bullet(element: etree._Element, paragraph: Paragraph) -> None:
    """Give a paragraph a bullet or a number, indented for its list level."""
    properties = element.get_or_add_pPr()
    indent = emu(28 * (paragraph.level + 1))
    properties.set("marL", str(int(indent)))
    properties.set("indent", str(-int(emu(22))))
    for old in properties.findall(qn("a:buNone")):
        properties.remove(old)
    if paragraph.bullet == "number":
        numbered = etree.SubElement(properties, qn("a:buAutoNum"))
        numbered.set("type", "arabicPeriod")
    else:
        bullet = etree.SubElement(properties, qn("a:buChar"))
        bullet.set("char", "•")


def _run(written: _Run, run: Run, faces: Typefaces) -> None:
    """Write one run's text and how it is drawn. A run drawn in one of the deck's own font
    files is named by that file's family, as PowerPoint finds it, and is bold or italic as
    that face is, or made so when no heavier or slanted face was declared.
    """
    written.text = run.text
    font = written.font
    weight = run.weight or (700 if run.bold else 400)
    face = faces.drawn(run.font, weight, run.italic, run.text)
    font.bold = run.bold if face is None else face.bold or (run.bold and face.weight < 600)
    font.italic = run.italic if face is None else face.italic or run.italic
    font.underline = run.underline
    if run.size is not None:
        font.size = Pt(run.size * POINTS_PER_PIXEL)
    if face is not None:
        font.name = face.typeface
    elif run.font is not None:
        font.name = run.font
    if run.colour is not None:
        paint(font.color, run.colour)
    properties = written._r.get_or_add_rPr()
    if run.spacing:
        properties.set("spc", str(round(run.spacing * POINTS_PER_PIXEL * 100)))
    if run.highlight is not None:
        _highlight(properties, run.highlight)
    if run.strike:
        properties.set("strike", "sngStrike")
    if run.script is not None:
        properties.set("baseline", "30000" if run.script == "super" else "-25000")
    if run.link is not None:
        written.hyperlink.address = run.link


LATER_THAN_HIGHLIGHT = (
    "a:uLnTx",
    "a:uLn",
    "a:uFillTx",
    "a:uFill",
    "a:latin",
    "a:ea",
    "a:cs",
    "a:sym",
    "a:hlinkClick",
    "a:hlinkMouseOver",
    "a:rtl",
    "a:extLst",
)
"""What follows a run's highlight in DrawingML, so the highlight goes before the first of them."""


def _highlight(properties: etree._Element, colour: str) -> None:
    """Mark a run's text with a background colour, as an inline chip or marked word has."""
    marked = etree.Element(qn("a:highlight"))
    shade = etree.SubElement(marked, qn("a:srgbClr"))
    shade.set("val", colour.lstrip("#")[:6].upper())
    if (alpha := alpha_of(colour)) is not None:
        etree.SubElement(shade, qn("a:alpha")).set("val", alpha)
    following = next(
        (found for tag in LATER_THAN_HIGHLIGHT if (found := properties.find(qn(tag))) is not None),
        None,
    )
    if following is not None:
        following.addprevious(marked)
    else:
        properties.append(marked)


ALIGNS = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}


ANCHORS = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE, "bottom": MSO_ANCHOR.BOTTOM}
