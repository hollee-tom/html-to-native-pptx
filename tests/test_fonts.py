"""A deck's own font files go inside its PowerPoint file, and each run names the face it was
drawn with as PowerPoint knows it, so the deck looks the same where the font is not installed.
"""

import io
import struct
import zipfile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from pptx import Presentation

from nativedeck.model import (
    Box,
    DeckFont,
    MeasuredDeck,
    MeasuredSlide,
    Paragraph,
    Run,
    TextItem,
)
from nativedeck.writer import deck_pptx

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def font(family: str, style: str, weight: int, *, postscript: bool = False, licence: int = 0):
    """A one-glyph font file: TrueType outlines, or PostScript ones as an `.otf` has."""
    built = FontBuilder(1000, isTTF=not postscript)
    built.setupGlyphOrder([".notdef", "A"])
    built.setupCharacterMap({65: "A"})
    if postscript:
        pen = T2CharStringPen(600, None)
        pen.moveTo((0, 0))
        pen.lineTo((300, 700))
        pen.lineTo((600, 0))
        pen.closePath()
        drawn = pen.getCharString()
        built.setupCFF(
            family.replace(" ", "") + "-" + style.replace(" ", ""),
            {"FullName": f"{family} {style}"},
            {".notdef": drawn, "A": drawn},
            {},
        )
    else:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((300, 700))
        pen.lineTo((600, 0))
        pen.closePath()
        glyph = pen.glyph()
        built.setupGlyf({".notdef": glyph, "A": glyph})
    built.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 0)})
    built.setupHorizontalHeader(ascent=800, descent=-200)
    built.setupNameTable({"familyName": family, "styleName": style})
    built.setupOS2(usWeightClass=weight, fsType=licence)
    built.setupPost()
    written = io.BytesIO()
    built.save(written)
    return written.getvalue()


def exported(*runs: Run, fonts: tuple[DeckFont, ...]) -> bytes:
    return deck_pptx(
        MeasuredDeck(
            width=1280,
            height=720,
            slides=(
                MeasuredSlide(
                    items=(
                        TextItem(
                            box=Box(x=40, y=40, width=600, height=200),
                            paragraphs=(Paragraph(runs=runs),),
                        ),
                    )
                ),
            ),
            fonts=fonts,
        )
    )


LIGHT = DeckFont(
    family="Brand Grotesk", weight=300, data=font("Brand Grotesk Light", "Regular", 300)
)
BOLD = DeckFont(
    family="Brand Grotesk", weight=700, data=font("Brand Grotesk", "Bold", 700, postscript=True)
)


def test_given_light_and_bold_faces_when_exported_then_runs_name_their_files_and_both_go_inside():
    pptx = exported(
        Run(text="Light ", font="Brand Grotesk", weight=300),
        Run(text="Bold", font="Brand Grotesk", weight=700, bold=True),
        fonts=(LIGHT, BOLD),
    )

    light, bold = Presentation(io.BytesIO(pptx)).slides[0].shapes[0].text_frame.paragraphs[0].runs
    assert (light.font.name, light.font.bold) == ("Brand Grotesk Light", False)
    assert (bold.font.name, bold.font.bold) == ("Brand Grotesk", True)
    with zipfile.ZipFile(io.BytesIO(pptx)) as package:
        presentation = package.read("ppt/presentation.xml").decode()
        assert 'embedTrueTypeFonts="1"' in presentation
        assert presentation.index("embeddedFontLst") < presentation.index("defaultTextStyle")
        assert 'Extension="fntdata"' in package.read("[Content_Types].xml").decode()
        parts = sorted(name for name in package.namelist() if name.endswith(".fntdata"))
        embedded = [_unwrapped(package.read(name)) for name in parts]
    assert [(f["name"].getDebugName(1), f["name"].getDebugName(2)) for f in embedded] == [
        ("Brand Grotesk Light", "Regular"),
        ("Brand Grotesk", "Bold"),
    ]
    assert all("glyf" in f for f in embedded)
    assert 'typeface="Brand Grotesk Light"' in presentation and "<p:regular" in presentation
    assert 'typeface="Brand Grotesk"' in presentation and "<p:bold" in presentation


def test_given_a_weight_between_faces_when_matched_then_css_picks_the_lighter_one_up_to_500():
    pptx = exported(Run(text="A", font="brand grotesk", weight=450), fonts=(LIGHT, BOLD))

    run = Presentation(io.BytesIO(pptx)).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Brand Grotesk Light"


def test_given_a_font_whose_licence_forbids_embedding_when_exported_then_it_is_named_not_carried():
    private = DeckFont(
        family="Private Sans", data=font("Private Sans", "Regular", 400, licence=0x0002)
    )

    pptx = exported(Run(text="A", font="Private Sans"), fonts=(private,))

    run = Presentation(io.BytesIO(pptx)).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Private Sans"
    with zipfile.ZipFile(io.BytesIO(pptx)) as package:
        assert not [name for name in package.namelist() if name.endswith(".fntdata")]
        assert "embeddedFontLst" not in package.read("ppt/presentation.xml").decode()


def test_given_a_font_the_deck_does_not_declare_when_exported_then_the_run_keeps_its_name():
    pptx = exported(
        Run(text="A", font="Georgia", italic=True),
        Run(text="B", font="Brand Grotesk", weight=300),
        fonts=(LIGHT, DeckFont(family="Broken", data=b"not a font")),
    )

    georgia, light = (
        Presentation(io.BytesIO(pptx)).slides[0].shapes[0].text_frame.paragraphs[0].runs
    )
    assert (georgia.font.name, georgia.font.italic) == ("Georgia", True)
    assert light.font.name == "Brand Grotesk Light"
    with zipfile.ZipFile(io.BytesIO(pptx)) as package:
        assert len([name for name in package.namelist() if name.endswith(".fntdata")]) == 1


def _unwrapped(eot: bytes) -> TTFont:
    """The TrueType font inside an EOT, checking the sizes its header states."""
    total, size, version = struct.unpack("<III", eot[:12])
    assert total == len(eot) and version == 0x00020001
    return TTFont(io.BytesIO(eot[-size:]))


def variable(family: str) -> bytes:
    """A variable font with a 100-800 weight axis whose default is its heaviest, as many are
    is: a viewer that draws the file as it is draws every run extra bold."""
    built = FontBuilder(1000, isTTF=True)
    built.setupGlyphOrder([".notdef", "A"])
    built.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((300, 700))
    pen.lineTo((600, 0))
    pen.closePath()
    glyph = pen.glyph()
    built.setupGlyf({".notdef": glyph, "A": glyph})
    built.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 0)})
    built.setupHorizontalHeader(ascent=800, descent=-200)
    built.setupNameTable({"familyName": family, "styleName": "Regular"})
    built.setupOS2(usWeightClass=800)
    built.setupPost()
    built.setupFvar([("wght", 100, 800, 800, "Weight")], [])
    built.setupGvar({})
    written = io.BytesIO()
    built.save(written)
    return written.getvalue()


def test_given_a_variable_font_when_exported_then_each_used_weight_is_cut_and_named():
    varied = DeckFont(family="Brand Var", weight=100, data=variable("Brand Var Variable"))

    pptx = exported(
        Run(text="Light ", font="Brand Var", weight=300),
        Run(text="Body ", font="Brand Var", weight=400),
        Run(text="Bold", font="Brand Var", weight=700, bold=True),
        fonts=(varied,),
    )

    runs = Presentation(io.BytesIO(pptx)).slides[0].shapes[0].text_frame.paragraphs[0].runs
    assert [(run.font.name, run.font.bold) for run in runs] == [
        ("Brand Var Light", False),
        ("Brand Var", False),
        ("Brand Var", True),
    ]
    with zipfile.ZipFile(io.BytesIO(pptx)) as package:
        parts = sorted(name for name in package.namelist() if name.endswith(".fntdata"))
        embedded = [_unwrapped(package.read(name)) for name in parts]
    assert sorted(
        (f["name"].getDebugName(1), f["name"].getDebugName(2), f["OS/2"].usWeightClass)
        for f in embedded
    ) == [
        ("Brand Var", "Bold", 700),
        ("Brand Var", "Regular", 400),
        ("Brand Var Light", "Regular", 300),
    ]
    assert not any("fvar" in f for f in embedded)
