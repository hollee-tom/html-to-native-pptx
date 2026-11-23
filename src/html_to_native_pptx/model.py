"""The measured deck: what the browser reports and what the writer consumes.

A deck becomes a PowerPoint file of editable objects: text boxes, tables, charts and shapes a
person can change in PowerPoint, not pictures of slides. To build one, Chromium draws each
slide and measures it: where every block sits, how its text is styled, what a table's cells and
a chart's numbers are. Those measurements, described here, go to the writer, which needs no
browser. Anything PowerPoint has no object for, such as a drawing or a gradient, is measured as
a picture of just that part, placed behind the native text.

All lengths are CSS pixels from the slide's top left corner. Colours are `#rrggbb`, or
`#rrggbbaa` when see-through: a tint such as `rgba(35,31,32,.08)` behind dark text must stay a
tint, and measuring it as a solid colour made the box the colour of its text.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Align = Literal["left", "center", "right", "justify"]
Script = Literal["super", "sub"]
Vertical = Literal["top", "middle", "bottom"]
ChartKind = Literal[
    "bar",
    "bar-stacked",
    "column",
    "column-stacked",
    "line",
    "area",
    "pie",
    "donut",
    "scatter",
    "combo",
    "waterfall",
    "funnel",
    "gauge",
]
Legend = Literal["top", "bottom", "right", "none"]


class Model(BaseModel):
    """Base of every measured type: immutable, and tolerant of keys a newer measurer adds."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class Box(Model):
    """Where something sits on its slide, in CSS pixels from the slide's top left corner."""

    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class Run(Model):
    """A stretch of text drawn the same way. A run whose text is a single newline is a line
    break.
    """

    text: str
    spacing: float = 0
    """Letter spacing in pixels, added after each character; negative tightens."""
    highlight: str | None = None
    """The background an inline element gives this text, such as a chip or a marked word."""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    script: Script | None = None
    colour: str | None = None
    size: float | None = Field(default=None, gt=0)
    font: str | None = None
    weight: int | None = Field(default=None, ge=1, le=1000)
    """The CSS weight it was drawn at, which picks the face: 300 is a Light file."""
    link: str | None = None


class Paragraph(Model):
    """One paragraph, heading, list item or quote line: its runs and how it is set."""

    runs: tuple[Run, ...] = ()
    align: Align = "left"
    level: int = Field(default=0, ge=0, le=8)
    bullet: Literal["disc", "number"] | None = None
    line_height: float | None = Field(default=None, gt=0)
    space_before: float = Field(default=0, ge=0)


class Insets(Model):
    """The space between a box's edge and its text, in pixels."""

    left: float = 0
    top: float = 0
    right: float = 0
    bottom: float = 0


class TextItem(Model):
    """A block of text with its own fill, rounded corners and outline when it has them.

    `wrap` is False for a block the browser set on one line, so a font drawn a little wider
    elsewhere does not break it onto two.
    """

    kind: Literal["text"] = "text"
    box: Box
    rotation: float = Field(default=0, ge=0, lt=360)
    """Degrees clockwise about the box's centre; the box is the element's own, unturned."""
    paragraphs: tuple[Paragraph, ...]
    insets: Insets = Insets()
    fill: str | None = None
    radius: float = Field(default=0, ge=0)
    line: str | None = None
    line_width: float = Field(default=0, ge=0)
    vertical: Vertical = "top"
    wrap: bool = True


class Border(Model):
    """One edge of a table cell."""

    width: float = Field(gt=0)
    colour: str


class Cell(Model):
    """One table cell, at its grid position, with how many rows and columns it spans."""

    row: int = Field(ge=0)
    column: int = Field(ge=0)
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)
    paragraphs: tuple[Paragraph, ...] = ()
    fill: str | None = None
    insets: Insets = Insets()
    vertical: Vertical = "middle"
    left: Border | None = None
    right: Border | None = None
    top: Border | None = None
    bottom: Border | None = None


class TableItem(Model):
    """A native table: column widths, row heights and every cell."""

    kind: Literal["table"] = "table"
    box: Box
    columns: tuple[float, ...] = Field(min_length=1)
    rows: tuple[float, ...] = Field(min_length=1)
    cells: tuple[Cell, ...]


class Series(Model):
    """One series of a chart: its name and a value per category, None where it has none."""

    name: str
    values: tuple[float | None, ...]


class ChartItem(Model):
    """A native chart, from a `figure[data-chart]` data table, in the design's colours."""

    kind: Literal["chart"] = "chart"
    box: Box
    chart: ChartKind
    categories: tuple[str, ...]
    series: tuple[Series, ...] = Field(min_length=1)
    legend: Legend = "bottom"
    labels: bool = False
    axis_min: float | None = None
    axis_max: float | None = None
    format: str | None = None
    colours: tuple[str, ...] = ()
    text_colour: str | None = None
    font: str | None = None
    size: float | None = Field(default=None, gt=0)
    caption: str | None = None


class PictureItem(Model):
    """A picture of one part of the slide PowerPoint has no object for, transparent around it."""

    kind: Literal["picture"] = "picture"
    box: Box
    png: bytes = Field(repr=False)


class ShapeItem(Model):
    """A rectangle, ellipse or line: a plain shape, or the background of a box."""

    kind: Literal["shape"] = "shape"
    box: Box
    rotation: float = Field(default=0, ge=0, lt=360)
    shape: Literal["rect", "ellipse", "line"] = "rect"
    fill: str | None = None
    line: str | None = None
    line_width: float = Field(default=0, ge=0)
    radius: float = Field(default=0, ge=0)


Item = Annotated[
    TextItem | TableItem | ChartItem | PictureItem | ShapeItem, Field(discriminator="kind")
]


class MeasuredSlide(Model):
    """One slide as measured: its background, as a colour or a picture, and everything on it
    from back to front.
    """

    background: str | None = None
    picture: bytes | None = Field(default=None, repr=False)
    items: tuple[Item, ...] = ()


class DeckFont(Model):
    """A font file the page loaded, as its `@font-face` rule names it."""

    family: str = Field(min_length=1, max_length=200)
    weight: int = Field(default=400, ge=1, le=1000)
    weight_max: int | None = Field(default=None, ge=1, le=1000)
    """The top of a variable face's declared weight range, e.g. 900 for `100 900`."""
    italic: bool = False
    data: bytes = Field(repr=False)


class MeasuredDeck(Model):
    """A whole deck as measured, at its canvas size, with the font files it loaded."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    slides: tuple[MeasuredSlide, ...] = Field(min_length=1)
    fonts: tuple[DeckFont, ...] = ()
