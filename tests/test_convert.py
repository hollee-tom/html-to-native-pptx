"""End-to-end: real HTML, real Chromium, the measurements and the file they become.

These need a Chromium Playwright can launch (see docker/dev.sh); they are skipped when none can
be started.
"""

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Emu

from nativedeck import NativedeckError, convert, measure
from nativedeck.cli import main
from nativedeck.model import ChartItem, ShapeItem, TableItem, TextItem

SLIDE = "<style>section{width:1280px;height:720px;position:relative;margin:0}body{margin:0}</style>"
CORPUS = Path(__file__).resolve().parent.parent / "corpus"


@pytest.fixture(scope="module", autouse=True)
def chromium() -> Iterator[None]:
    """Skip the module when no browser can be launched."""
    try:
        measure(SLIDE + "<section></section>")
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"no Chromium: {type(error).__name__}")
    yield


def texts(html: str) -> list[TextItem]:
    return [i for s in measure(SLIDE + html).slides for i in s.items if isinstance(i, TextItem)]


def test_given_an_inline_chip_when_measured_then_the_paragraph_stays_whole_with_a_highlight():
    (item,) = texts(
        "<section><p>Build is <span style='background:#fc0;padding:0 8px'>passing</span> now</p></section>"
    )

    assert len(item.paragraphs) == 1
    assert any(run.highlight == "#ffcc00" for run in item.paragraphs[0].runs)


def test_given_opacity_on_an_ancestor_when_measured_then_it_is_folded_into_the_colour_alpha():
    (item,) = texts(
        "<section><div style='opacity:.5'><p style='color:#000'>Faded</p></div></section>"
    )

    assert item.paragraphs[0].runs[0].colour == "#00000080"


def test_given_letter_spacing_when_written_then_the_run_has_spc(tmp_path: Path) -> None:
    out = convert(
        SLIDE + "<section><p style='letter-spacing:4px'>SPACED</p></section>", tmp_path / "a.pptx"
    )

    with zipfile.ZipFile(out) as package:
        assert 'spc="300"' in package.read("ppt/slides/slide1.xml").decode()


def test_given_a_border_on_one_side_when_measured_then_it_is_a_strip_not_an_outline():
    deck = measure(
        SLIDE
        + "<section><div style='width:200px;height:100px;border-top:6px solid #f00'></div></section>"
    )

    strips = [i for i in deck.slides[0].items if isinstance(i, ShapeItem)]
    assert [(round(s.box.height), s.fill) for s in strips] == [(6, "#ff0000")]


def test_given_shapes_when_written_then_they_carry_no_theme_style(tmp_path: Path) -> None:
    out = convert(
        SLIDE
        + "<section><div style='width:200px;height:100px;background:rgba(0,0,0,.3)'></div></section>",
        tmp_path / "a.pptx",
    )

    with zipfile.ZipFile(out) as package:
        assert "<p:style>" not in package.read("ppt/slides/slide1.xml").decode()


def test_given_a_table_when_written_then_it_has_no_grid_style_and_bare_sides_are_no_line(
    tmp_path: Path,
) -> None:
    out = convert(
        SLIDE
        + "<section><table><tr><td style='border-bottom:2px solid #000'>A</td><td>B</td></tr></table></section>",
        tmp_path / "a.pptx",
    )

    with zipfile.ZipFile(out) as package:
        xml = package.read("ppt/slides/slide1.xml").decode()
    assert "{2D5ABB26-0587-4C30-8999-92F81FD0307C}" in xml
    assert xml.count("<a:noFill/>") >= 7


def test_given_a_data_chart_figure_when_written_then_it_is_a_native_chart(tmp_path: Path) -> None:
    html = (
        "<section><figure data-chart='column' style='margin:0;width:600px;height:300px'>"
        "<table data-chart-data><thead><tr><th></th><th>S</th></tr></thead>"
        "<tbody><tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr></tbody></table></figure></section>"
    )
    deck = measure(SLIDE + html)
    out = convert(SLIDE + html, tmp_path / "a.pptx")

    assert any(isinstance(i, ChartItem) for i in deck.slides[0].items)
    assert Presentation(str(out)).slides[0].shapes[0].has_chart


def test_given_a_wrapper_with_no_height_when_measured_then_its_positioned_children_are_kept():
    items = texts(
        "<section><div style='height:0'><p style='position:absolute;top:20px'>Inside</p></div></section>"
    )

    assert [i.paragraphs[0].runs[0].text for i in items] == ["Inside"]


def test_given_a_quote_with_bare_text_and_a_cite_when_measured_then_both_are_kept():
    (item,) = texts(
        "<section><blockquote>Said it.<cite style='display:block'>Someone</cite></blockquote></section>"
    )

    assert [p.runs[0].text for p in item.paragraphs] == ["Said it.", "Someone"]


def test_given_a_deck_with_font_files_when_converted_then_the_browsers_fonts_are_embedded(
    tmp_path: Path,
) -> None:
    deck = measure(CORPUS / "deck.html")

    assert {f.family for f in deck.fonts} == {"Inter", "DM Serif Display", "IBM Plex Mono"}
    out = convert(CORPUS / "deck.html", tmp_path / "a.pptx")
    with zipfile.ZipFile(out) as package:
        assert any(name.endswith(".fntdata") for name in package.namelist())
    plain = convert(CORPUS / "deck.html", tmp_path / "b.pptx", embed_fonts=False)
    with zipfile.ZipFile(plain) as package:
        assert not any(name.endswith(".fntdata") for name in package.namelist())


def test_given_the_corpus_when_converted_then_every_slide_is_written_at_the_canvas_size(
    tmp_path: Path,
) -> None:
    out = convert(CORPUS / "deck.html", tmp_path / "a.pptx")

    presentation = Presentation(str(out))
    assert len(presentation.slides) == 21
    assert presentation.slide_width == Emu(1280 * 9525)


def test_given_a_selector_that_matches_nothing_when_converted_then_it_says_so(
    tmp_path: Path,
) -> None:
    with pytest.raises(NativedeckError, match="no element matches"):
        convert(SLIDE + "<section></section>", tmp_path / "a.pptx", slide_selector=".missing")


def test_given_the_cli_when_run_then_it_writes_the_file(tmp_path: Path) -> None:
    page = tmp_path / "d.html"
    page.write_text(SLIDE + "<section><h1>Hi</h1></section><section><h1>There</h1></section>")

    assert main([str(page), "-o", str(tmp_path / "d.pptx")]) == 0
    assert len(Presentation(io.BytesIO((tmp_path / "d.pptx").read_bytes())).slides) == 2


def test_given_the_corpus_when_measured_then_its_two_tables_are_native() -> None:
    deck = measure(CORPUS / "deck.html")

    assert sum(isinstance(i, TableItem) for s in deck.slides for i in s.items) == 2
