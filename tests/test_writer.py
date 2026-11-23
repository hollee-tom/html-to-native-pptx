"""A measured deck becomes a PowerPoint file of editable objects: text boxes with their runs,
native tables with merged cells, native charts with their numbers and colours, shapes and
pictures, each where the browser measured it.
"""

import base64
import io

from pptx import Presentation
from pptx.chart.plot import BarPlot, LinePlot
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Emu

from html_to_native_pptx.model import (
    Border,
    Box,
    Cell,
    ChartItem,
    MeasuredDeck,
    MeasuredSlide,
    Paragraph,
    PictureItem,
    Run,
    Series,
    ShapeItem,
    TableItem,
    TextItem,
)
from html_to_native_pptx.writer import deck_pptx

PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def opened(*slides: MeasuredSlide) -> Presentation:
    return Presentation(io.BytesIO(deck_pptx(MeasuredDeck(width=1280, height=720, slides=slides))))


def chart(kind: str, series: int = 2) -> ChartItem:
    return ChartItem(
        box=Box(x=100, y=100, width=640, height=360),
        chart=kind,
        categories=("Q1", "Q2", "Q3"),
        series=tuple(Series(name=f"S{at}", values=(1.0 + at, 2.0, None)) for at in range(series)),
        colours=("#4B3BFF", "#FF7A59"),
        labels=True,
        format="percent",
    )


def test_given_a_text_block_when_written_then_it_is_a_text_box_at_its_place_with_its_runs():
    deck = opened(
        MeasuredSlide(
            background="#F6F4EF",
            items=(
                TextItem(
                    box=Box(x=88, y=268, width=740, height=160),
                    paragraphs=(
                        Paragraph(
                            runs=(
                                Run(
                                    text="Big ", bold=True, size=72, colour="#16181D", font="Inter"
                                ),
                                Run(text="idea", italic=True, strike=True, script="super"),
                                Run(text="\n"),
                                Run(text="second line", link="https://example.com"),
                            ),
                            align="center",
                        ),
                        Paragraph(runs=(Run(text="point"),), bullet="disc", level=1),
                    ),
                ),
            ),
        )
    )

    shape = deck.slides[0].shapes[0]
    assert deck.slide_width == Emu(1280 * 9525) and deck.slide_height == Emu(720 * 9525)
    assert (shape.left, shape.top, shape.width) == (
        Emu(88 * 9525),
        Emu(268 * 9525),
        Emu(740 * 9525),
    )
    first, second = shape.text_frame.paragraphs
    runs = first.runs
    assert [run.text for run in runs] == ["Big ", "idea", "second line"]
    assert runs[0].font.bold and runs[0].font.size.pt == 54 and runs[0].font.name == "Inter"
    assert str(runs[0].font.color.rgb) == "16181D"
    assert runs[1]._r.rPr.get("strike") == "sngStrike" and runs[1]._r.rPr.get("baseline") == "30000"
    assert runs[2].hyperlink.address == "https://example.com"
    assert (
        second.level == 1
        and second._p.pPr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}buChar")
        is not None
    )


def test_given_a_table_with_spans_when_written_then_it_is_a_native_table_with_merges():
    deck = opened(
        MeasuredSlide(
            items=(
                TableItem(
                    box=Box(x=88, y=200, width=600, height=120),
                    columns=(200, 200, 200),
                    rows=(40, 40, 40),
                    cells=(
                        Cell(
                            row=0,
                            column=0,
                            colspan=2,
                            fill="#16181D",
                            paragraphs=(Paragraph(runs=(Run(text="Head", colour="#FFFFFF"),)),),
                            bottom=Border(width=1, colour="#D9D6CE"),
                        ),
                        Cell(row=0, column=2, paragraphs=(Paragraph(runs=(Run(text="C"),)),)),
                        Cell(
                            row=1,
                            column=0,
                            rowspan=2,
                            paragraphs=(Paragraph(runs=(Run(text="R"),)),),
                        ),
                    ),
                ),
            )
        )
    )

    frame = deck.slides[0].shapes[0]
    table = frame.table
    assert frame.has_table and len(table.rows) == 3 and len(table.columns) == 3
    assert table.cell(0, 0).is_merge_origin and table.cell(0, 1).is_spanned
    assert table.cell(1, 0).is_merge_origin and table.cell(2, 0).is_spanned
    assert table.cell(0, 0).text == "Head" and str(table.cell(0, 0).fill.fore_color.rgb) == "16181D"
    assert (
        table.cell(0, 0)._tc.tcPr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}lnB")
        is not None
    )
    assert not table.first_row


def test_given_each_chart_kind_when_written_then_it_is_a_native_chart_of_the_closest_type():
    expected = {
        "bar": XL_CHART_TYPE.BAR_CLUSTERED,
        "bar-stacked": XL_CHART_TYPE.BAR_STACKED,
        "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
        "column-stacked": XL_CHART_TYPE.COLUMN_STACKED,
        "line": XL_CHART_TYPE.LINE_MARKERS,
        "area": XL_CHART_TYPE.AREA,
        "pie": XL_CHART_TYPE.PIE,
        "donut": XL_CHART_TYPE.DOUGHNUT,
        "scatter": XL_CHART_TYPE.XY_SCATTER,
        "waterfall": XL_CHART_TYPE.COLUMN_STACKED,
        "funnel": XL_CHART_TYPE.BAR_CLUSTERED,
        "gauge": XL_CHART_TYPE.DOUGHNUT,
    }
    deck = opened(*(MeasuredSlide(items=(chart(kind),)) for kind in expected))

    for slide, kind in zip(deck.slides, expected.values(), strict=True):
        frame = slide.shapes[0]
        assert frame.has_chart and frame.chart.chart_type == kind


def test_given_a_column_chart_when_written_then_its_series_numbers_and_colours_are_kept():
    frame = opened(MeasuredSlide(items=(chart("column"),))).slides[0].shapes[0]

    plot = frame.chart.plots[0]
    assert [series.name for series in plot.series] == ["S0", "S1"]
    assert list(plot.series[0].values) == [1.0, 2.0, None]
    assert str(plot.series[1].format.fill.fore_color.rgb) == "FF7A59"
    assert plot.has_data_labels and frame.chart.value_axis.tick_labels.number_format == '#,##0"%"'


def test_given_a_combo_chart_when_written_then_later_series_are_lines_over_the_columns():
    frame = opened(MeasuredSlide(items=(chart("combo", 3),))).slides[0].shapes[0]

    plots = frame.chart.plots
    assert len(plots) == 2 and len(plots[0].series) == 1 and len(plots[1].series) == 2
    assert isinstance(plots[0], BarPlot)
    assert isinstance(plots[1], LinePlot)


def test_given_a_waterfall_when_written_then_an_invisible_base_holds_each_step_up():
    item = chart("waterfall").model_copy(
        update={"series": (Series(name="Change", values=(5.0, -2.0, 4.0)),)}
    )
    plot = opened(MeasuredSlide(items=(item,))).slides[0].shapes[0].chart.plots[0]

    assert list(plot.series[0].values) == [0.0, 3.0, 3.0]
    assert list(plot.series[1].values) == [5.0, 2.0, 4.0]


def test_given_shapes_and_pictures_when_written_then_each_is_its_own_object():
    deck = opened(
        MeasuredSlide(
            picture=PIXEL,
            items=(
                ShapeItem(box=Box(x=0, y=0, width=96, height=8), fill="#4B3BFF"),
                ShapeItem(
                    box=Box(x=10, y=10, width=50, height=50),
                    shape="ellipse",
                    line="#000000",
                    line_width=2,
                ),
                PictureItem(box=Box(x=860, y=120, width=360, height=360), png=PIXEL),
            ),
        )
    )

    kinds = [shape.shape_type for shape in deck.slides[0].shapes]
    assert kinds == [
        MSO_SHAPE_TYPE.PICTURE,
        MSO_SHAPE_TYPE.AUTO_SHAPE,
        MSO_SHAPE_TYPE.AUTO_SHAPE,
        MSO_SHAPE_TYPE.PICTURE,
    ]
    assert str(deck.slides[0].shapes[1].fill.fore_color.rgb) == "4B3BFF"


def test_given_a_rounded_one_line_label_when_written_then_it_is_a_rounded_shape_that_never_wraps():
    deck = opened(
        MeasuredSlide(
            items=(
                TextItem(
                    box=Box(x=10, y=10, width=120, height=32),
                    paragraphs=(Paragraph(runs=(Run(text="Paid social"),)),),
                    fill="#E3E208",
                    radius=999,
                    wrap=False,
                ),
            )
        )
    )

    shape = deck.slides[0].shapes[0]
    assert shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE and shape.adjustments[0] == 0.5
    assert shape.text_frame.text == "Paid social" and shape.text_frame.word_wrap is False
    assert str(shape.fill.fore_color.rgb) == "E3E208"


def test_given_a_see_through_tint_when_written_then_it_stays_a_tint_not_a_solid_box():
    """An 8% charcoal box behind charcoal text must not become charcoal on charcoal."""
    deck = opened(
        MeasuredSlide(
            background="#F4F0E8",
            items=(
                TextItem(
                    box=Box(x=40, y=40, width=300, height=40),
                    paragraphs=(Paragraph(runs=(Run(text="Services", colour="#231f20"),)),),
                    fill="#231f2014",
                ),
                ShapeItem(
                    box=Box(x=40, y=120, width=300, height=2),
                    shape="rect",
                    fill=None,
                    line="#ddd9d080",
                    line_width=1,
                ),
            ),
        )
    )

    box, rule = deck.slides[0].shapes
    namespace = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    tint = box.fill._xPr.find(f"{namespace}solidFill/{namespace}srgbClr")
    assert tint.get("val") == "231F20"
    assert tint.find(f"{namespace}alpha").get("val") == "7843"
    outline = rule.line._ln.find(f"{namespace}solidFill/{namespace}srgbClr")
    assert outline.find(f"{namespace}alpha").get("val") == "50196"
    text = box.text_frame.paragraphs[0].runs[0].font.color
    assert str(text.rgb) == "231F20" and text._color._xClr.find(f"{namespace}alpha") is None


def test_given_a_chart_with_no_rows_when_written_then_the_deck_still_exports_without_it():
    """The page draws nothing for a chart without rows; it must not fail the whole download."""
    empty = ChartItem(
        box=Box(x=100, y=100, width=640, height=360),
        chart="line",
        categories=(),
        series=(Series(name="S1", values=()),),
    )

    deck = opened(MeasuredSlide(items=(empty,)))

    assert not [shape for shape in deck.slides[0].shapes if shape.has_chart]


def test_given_spaced_highlighted_turned_text_when_written_then_each_is_native():
    """Letter spacing, a chip's background and a turned card survive as PowerPoint's own."""
    deck = opened(
        MeasuredSlide(
            items=(
                TextItem(
                    box=Box(x=40, y=40, width=300, height=40),
                    rotation=356,
                    paragraphs=(
                        Paragraph(
                            runs=(
                                Run(text="LABEL", spacing=2.4),
                                Run(text="\u00a0", spacing=-1.0),
                                Run(text="OPEN", colour="#ffffff", highlight="#fc520280"),
                            )
                        ),
                    ),
                ),
                ShapeItem(box=Box(x=40, y=120, width=200, height=100), fill="#0f6242", rotation=4),
            )
        )
    )

    card, shape = deck.slides[0].shapes
    namespace = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    label, gap, chip = card.text_frame.paragraphs[0].runs
    assert card.rotation == 356 and shape.rotation == 4
    assert label._r.rPr.get("spc") == "180" and gap._r.rPr.get("spc") == "-75"
    marked = chip._r.rPr.find(f"{namespace}highlight/{namespace}srgbClr")
    assert marked.get("val") == "FC5202" and marked.find(f"{namespace}alpha").get("val") == "50196"
    children = [element.tag.split("}")[1] for element in chip._r.rPr]
    assert children.index("highlight") < children.index("latin") if "latin" in children else True


def test_given_a_reversed_axis_and_fractions_when_charted_then_bounds_drop_and_decimals_stay():
    item = chart("column").model_copy(
        update={
            "axis_min": 10.0,
            "axis_max": 2.0,
            "series": (Series(name="S0", values=(1.5, 2.25, None)),),
        }
    )

    frame = opened(MeasuredSlide(items=(item,))).slides[0].shapes[0]

    axis = frame.chart.value_axis
    assert axis.minimum_scale is None and axis.maximum_scale is None
    assert axis.tick_labels.number_format == '#,##0.0#"%"'


def test_given_a_tint_and_a_ruled_table_when_written_then_no_theme_shadow_or_grid_is_added():
    """A see-through overlay must not pick up the theme's shadow, and a table side the page
    leaves bare must not pick up the default table style's grid."""
    deck = opened(
        MeasuredSlide(
            items=(
                ShapeItem(box=Box(x=0, y=0, width=1280, height=720), fill="#00000080"),
                TableItem(
                    box=Box(x=100, y=100, width=400, height=60),
                    columns=(200, 200),
                    rows=(60,),
                    cells=(
                        Cell(
                            row=0,
                            column=0,
                            paragraphs=(Paragraph(runs=(Run(text="A"),)),),
                            bottom=Border(width=1, colour="#ffffff"),
                        ),
                    ),
                ),
            )
        )
    )

    overlay, frame = deck.slides[0].shapes
    namespace = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    assert (
        overlay._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style")
        is None
    )
    table = frame.table
    assert (
        table._tbl.tblPr.find(f"{namespace}tableStyleId").text
        == "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"
    )
    sides = table.cell(0, 0)._tc.tcPr
    assert sides.find(f"{namespace}lnB/{namespace}solidFill") is not None
    assert all(
        sides.find(f"{namespace}{tag}/{namespace}noFill") is not None
        for tag in ("lnL", "lnR", "lnT")
    )


def test_given_a_deck_with_pictures_and_fonts_when_sent_as_json_then_it_reads_back_equal():
    from html_to_native_pptx.model import DeckFont, MeasuredDeck, MeasuredSlide

    deck = MeasuredDeck(
        width=1280,
        height=720,
        slides=(MeasuredSlide(picture=b"\x89PNG\xff\x00binary"),),
        fonts=(DeckFont(family="Inter", data=b"\x00\x01\x00\x00\xff"),),
    )

    assert MeasuredDeck.model_validate_json(deck.model_dump_json()) == deck
