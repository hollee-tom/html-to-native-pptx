"""The deck's own font files, put inside an exported PowerPoint file.

A PowerPoint file names its fonts and the computer opening it supplies them, so a deck in a
web font most people lack opens in a fallback. PowerPoint can carry the fonts inside the
file. python-pptx cannot write them, so this module does, after the file is written.

Each font the deck declares with `@font-face` is read once. A run is pointed at the face the
browser drew it with, by the family name inside that file. That name is what PowerPoint
matches, and it differs from the CSS family for most weights: the 300 face of "Fraunces"
is a family called "Fraunces Light". The faces runs used are then embedded,
unless a face's licence forbids embedding, in which case it is only named.

PowerPoint stores an embedded font as uncompressed Embedded OpenType (EOT): a short header
before TrueType data. A font with PostScript (CFF) outlines, as most `.otf` files have, is
converted to TrueType outlines first. Every face of a family name sits in one of four slots,
regular, bold, italic and bold italic, so a name with more faces than that keeps the first.
"""

from __future__ import annotations

import io
import logging
import re
import struct
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, TTLibError, newTable
from fontTools.varLib import instancer
from lxml import etree

from nativedeck.model import DeckFont

logger = logging.getLogger(__name__)

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
FONT_RELATIONSHIP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
FONT_DATA = "application/x-fontdata"
FOLLOWING = (
    "custShowLst",
    "photoAlbum",
    "custDataLst",
    "kinsoku",
    "defaultTextStyle",
    "modifyVerifier",
    "extLst",
)
"""What may follow `embeddedFontLst` in a presentation, in schema order."""
SLOTS = {(False, False): "regular", (True, False): "bold", (False, True): "italic"}
RESTRICTED = 0x0002
"""The licence bit that forbids embedding, unless a preview or editable bit is also set."""
EMBEDDABLE = 0x0004 | 0x0008
BITMAP_ONLY = 0x0200
EOT_VERSION = 0x00020001
EOT_MAGIC = 0x504C


@dataclass(frozen=True)
class Face:
    """A font file as PowerPoint knows it: its family name, whether it is the bold or italic
    of that name, its weight, and the embedded form, or None when it may only be named.
    """

    typeface: str
    bold: bool
    italic: bool
    weight: int
    embedded: bytes | None = field(repr=False)
    characters: frozenset[int] = field(default=frozenset(), repr=False)


@dataclass
class Variable:
    """A variable font: one file holding a range of weights. PowerPoint and most other
    viewers draw such a file at its default weight, which for many web fonts is the
    heaviest, so each weight a run uses is cut out as a fixed font of its own and named as
    PowerPoint names weights: "Inter" for 400 and its bold for 700, "Inter Light" for 300.
    """

    font: TTFont = field(repr=False)
    family: str
    allowed: bool
    cut: dict[tuple[int, bool], Face] = field(default_factory=dict)

    def covers(self, text: str) -> int:
        """How many of `text`'s characters this file has a glyph for."""
        return _coverage(self.font, text)

    def at(self, weight: int, italic: bool) -> Face:
        """The fixed font cut at `weight` (slanted if asked and possible), made once."""
        axes = {axis.axisTag: axis for axis in self.font["fvar"].axes}
        if "wght" in axes:
            weight = round(min(max(weight, axes["wght"].minValue), axes["wght"].maxValue))
        else:
            weight = self.font["OS/2"].usWeightClass
        slanted = italic and "ital" in axes
        if (weight, slanted) in self.cut:
            return self.cut[(weight, slanted)]
        location = {tag: axis.defaultValue for tag, axis in axes.items()}
        if "wght" in axes:
            location["wght"] = weight
        if slanted:
            location["ital"] = axes["ital"].maxValue
        bold = weight == 700
        typeface = self.family if weight in (400, 700) else f"{self.family} {_weight_name(weight)}"
        embedded = None
        if self.allowed:
            try:
                fixed = instancer.instantiateVariableFont(self.font, location)
                renamed(fixed, typeface, weight, bold, slanted)
                embedded = _eot(_truetype(fixed))
            except (TTLibError, KeyError, ValueError, AssertionError, struct.error) as error:
                logger.warning("font not embedded: %s", type(error).__name__)
        face = Face(typeface=typeface, bold=bold, italic=slanted, weight=weight, embedded=embedded)
        self.cut[(weight, slanted)] = face
        return face


@dataclass
class Typefaces:
    """The deck's declared faces, found by the CSS family, weight and style a run was drawn
    with, remembering each face a run used so only those are embedded.
    """

    declared: dict[str, list[tuple[DeckFont, Face | Variable]]] = field(default_factory=dict)
    used: dict[tuple[str, bool, bool], Face] = field(default_factory=dict)

    @classmethod
    def of(cls, fonts: Iterable[DeckFont]) -> Typefaces:
        """The faces of every readable font file in `fonts`, ready to be matched to runs."""
        found = cls()
        for font in fonts:
            face = _face(font)
            if face is not None:
                found.declared.setdefault(font.family.casefold(), []).append((font, face))
        return found

    def drawn(self, family: str | None, weight: int, italic: bool, text: str = "") -> Face | None:
        """The face the browser drew a run with, as CSS font matching picks it: the same style
        first, then the nearest weight, lighter first at or below 500 and heavier above. A
        variable font gives the run's own weight. Several files of one family and weight, as a
        font service's per-script subsets are, are told apart by which holds the run's text.
        """
        faces = self.declared.get((family or "").casefold())
        if not faces:
            return None

        def distance(entry: tuple[DeckFont, Face | Variable]) -> tuple[int, int, int, int]:
            font, face = entry
            top = font.weight_max or font.weight
            if font.weight <= weight <= top:
                gap, preferred = 0, True
            else:
                gap = font.weight - weight if weight < font.weight else weight - top
                preferred = (weight <= 500) == (font.weight <= weight)
            held = face.covers(text) if isinstance(face, Variable) else _held(face, text)
            return (font.italic != italic, 0 if preferred else 1, gap, -held)

        source = min(faces, key=distance)[1]
        face = source.at(weight, italic) if isinstance(source, Variable) else source
        self.used.setdefault((face.typeface, face.bold, face.italic), face)
        return face

    def embedded(self, pptx: bytes) -> bytes:
        """The written file with every used face that may be embedded inside it."""
        slots: dict[str, dict[str, bytes]] = {}
        for face in self.used.values():
            if face.embedded is None:
                continue
            slot = SLOTS.get((face.bold, face.italic), "boldItalic")
            slots.setdefault(face.typeface, {}).setdefault(slot, face.embedded)
        return _with_fonts(pptx, slots) if slots else pptx


def _coverage(font: TTFont, text: str) -> int:
    """How many distinct characters of `text` the font's character map holds."""
    cmap = font.getBestCmap() or {}
    return sum(1 for char in set(text) if ord(char) in cmap)


def _face(font: DeckFont) -> Face | Variable | None:
    """The file's family name, style and embedded form, or a variable font to cut weights
    from; None for a file that is not a font.
    """
    try:
        parsed = TTFont(io.BytesIO(font.data))
        parsed.flavor = None
        names = parsed["name"]
        family = names.getDebugName(16) or names.getDebugName(1)
        style = (names.getDebugName(2) or "Regular").casefold()
        os2 = parsed["OS/2"]
    except (TTLibError, KeyError, ValueError, AssertionError, struct.error) as error:
        logger.warning("font unreadable: %s", type(error).__name__)
        return None
    if not family:
        return None
    licence = os2.fsType
    allowed = not (licence & BITMAP_ONLY) and (
        not licence & RESTRICTED or bool(licence & EMBEDDABLE)
    )
    if "fvar" in parsed:
        return Variable(font=parsed, family=VARIABLE_SUFFIX.sub("", family), allowed=allowed)
    family = names.getDebugName(1) or family
    bold = "bold" in style
    italic = "italic" in style or "oblique" in style
    embedded = None
    if allowed:
        try:
            embedded = _eot(_truetype(parsed))
        except (TTLibError, KeyError, ValueError, AssertionError, struct.error) as error:
            logger.warning("font not embedded: %s", type(error).__name__)
    return Face(
        typeface=family,
        bold=bold,
        italic=italic,
        weight=os2.usWeightClass,
        embedded=embedded,
        characters=frozenset(parsed.getBestCmap() or {}),
    )


WEIGHT_NAMES = {
    100: "Thin",
    200: "ExtraLight",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black",
}
VARIABLE_SUFFIX = re.compile(r"\s+(Variable|VF|Var)$", re.IGNORECASE)


def _held(face: Face, text: str) -> int:
    """How many distinct characters of `text` a fixed face has a glyph for."""
    return sum(1 for char in set(text) if ord(char) in face.characters)


def _weight_name(weight: int) -> str:
    """The usual name of a weight; a weight between the named ones keeps its number."""
    return WEIGHT_NAMES.get(weight, str(weight))


def renamed(font: TTFont, typeface: str, weight: int, bold: bool, italic: bool) -> None:
    """Name a weight cut from a variable font as a fixed font of its own, so PowerPoint
    matches it by `typeface` and its regular, bold or italic slot.
    """
    style = ("Bold " if bold else "") + ("Italic" if italic else "")
    style = style.strip() or "Regular"
    full = typeface if style == "Regular" else f"{typeface} {style}"
    names = font["name"]
    for name_id in (16, 17, 21, 22, 25):
        names.removeNames(nameID=name_id)
    for name_id, value in (
        (1, typeface),
        (2, style),
        (4, full),
        (6, re.sub(r"[^A-Za-z0-9-]", "", full.replace(" ", "-"))[:63]),
    ):
        names.setName(value, name_id, 3, 1, 0x409)
        names.setName(value, name_id, 1, 0, 0)
    os2 = font["OS/2"]
    os2.usWeightClass = weight
    os2.fsSelection = (os2.fsSelection & ~0b1100001) | (
        (1 << 5 if bold else 0) | (1 if italic else 0) | (0 if bold or italic else 1 << 6)
    )
    font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)


def _truetype(font: TTFont) -> TTFont:
    """The font with TrueType outlines, converted from PostScript ones when it has those."""
    if "glyf" in font:
        return font
    order = font.getGlyphOrder()
    drawn = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = {}
    for name in order:
        pen = TTGlyphPen(drawn)
        drawn[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        glyf[name] = pen.glyph()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf
    del font["CFF "]
    if "VORG" in font:
        del font["VORG"]
    font.sfntVersion = "\x00\x01\x00\x00"
    font["head"].glyphDataFormat = 0
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    maxp.maxZones = 1
    for limit in (
        "maxPoints",
        "maxContours",
        "maxCompositePoints",
        "maxCompositeContours",
        "maxTwilightPoints",
        "maxStorage",
        "maxFunctionDefs",
        "maxInstructionDefs",
        "maxStackElements",
        "maxSizeOfInstructions",
        "maxComponentElements",
        "maxComponentDepth",
    ):
        setattr(maxp, limit, 0)
    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = order
    written = io.BytesIO()
    font.save(written)
    return TTFont(io.BytesIO(written.getvalue()))


def _eot(font: TTFont) -> bytes:
    """Uncompressed EOT, version 2.1: the header PowerPoint reads, then the TrueType data."""
    data = io.BytesIO()
    font.save(data)
    content = data.getvalue()
    os2, names = font["OS/2"], font["name"]
    panose = os2.panose
    strings = b""
    for name_id in (1, 2, 5, 4):  # family, style, version, full name
        value = (names.getDebugName(name_id) or "").encode("utf-16-le")
        strings += struct.pack("<HH", 0, len(value)) + value
    strings += struct.pack("<HH", 0, 0)  # padding, then an empty root string
    header = struct.pack(
        "<III10sBBIHH4I2II4I",
        len(content),
        EOT_VERSION,
        0,
        bytes(
            [
                panose.bFamilyType,
                panose.bSerifStyle,
                panose.bWeight,
                panose.bProportion,
                panose.bContrast,
                panose.bStrokeVariation,
                panose.bArmStyle,
                panose.bLetterForm,
                panose.bMidline,
                panose.bXHeight,
            ]
        ),
        1,
        os2.fsSelection & 1,
        os2.usWeightClass,
        os2.fsType,
        EOT_MAGIC,
        os2.ulUnicodeRange1,
        os2.ulUnicodeRange2,
        os2.ulUnicodeRange3,
        os2.ulUnicodeRange4,
        getattr(os2, "ulCodePageRange1", 0),
        getattr(os2, "ulCodePageRange2", 0),
        font["head"].checkSumAdjustment,
        0,
        0,
        0,
        0,
    )
    total = 4 + len(header) + len(strings) + len(content)
    return struct.pack("<I", total) + header + strings + content


def _with_fonts(pptx: bytes, slots: dict[str, dict[str, bytes]]) -> bytes:
    """The package with each family's slots as font parts, related from the presentation and
    listed in its `embeddedFontLst`.
    """
    with zipfile.ZipFile(io.BytesIO(pptx)) as package:
        files = {item.filename: package.read(item.filename) for item in package.infolist()}
    types = etree.fromstring(files["[Content_Types].xml"])
    if not any(d.get("Extension") == "fntdata" for d in types.iter(f"{{{TYPES}}}Default")):
        etree.SubElement(types, f"{{{TYPES}}}Default", Extension="fntdata", ContentType=FONT_DATA)
    relationships = etree.fromstring(files["ppt/_rels/presentation.xml.rels"])
    taken = {relationship.get("Id") for relationship in relationships}
    presentation = etree.fromstring(files["ppt/presentation.xml"])
    presentation.set("embedTrueTypeFonts", "1")
    listed = etree.Element(f"{{{P}}}embeddedFontLst")
    number = 0
    for typeface, faces in slots.items():
        entry = etree.SubElement(listed, f"{{{P}}}embeddedFont")
        etree.SubElement(entry, f"{{{P}}}font", typeface=typeface, charset="0")
        for slot in ("regular", "bold", "italic", "boldItalic"):
            if slot not in faces:
                continue
            number += 1
            identifier = _free(taken)
            files[f"ppt/fonts/font{number}.fntdata"] = faces[slot]
            etree.SubElement(
                relationships,
                f"{{{PACKAGE}}}Relationship",
                Id=identifier,
                Type=FONT_RELATIONSHIP,
                Target=f"fonts/font{number}.fntdata",
            )
            etree.SubElement(entry, f"{{{P}}}{slot}").set(f"{{{R}}}id", identifier)
    following = next(
        (found for name in FOLLOWING if (found := presentation.find(f"{{{P}}}{name}")) is not None),
        None,
    )
    if following is not None:
        following.addprevious(listed)
    else:
        presentation.append(listed)
    files["[Content_Types].xml"] = _xml(types)
    files["ppt/_rels/presentation.xml.rels"] = _xml(relationships)
    files["ppt/presentation.xml"] = _xml(presentation)
    written = io.BytesIO()
    with zipfile.ZipFile(written, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", files.pop("[Content_Types].xml"))
        for name, content in files.items():
            package.writestr(name, content)
    return written.getvalue()


def _free(taken: set[str | None]) -> str:
    number = 1
    while f"rIdFont{number}" in taken:
        number += 1
    identifier = f"rIdFont{number}"
    taken.add(identifier)
    return identifier


def _xml(element: etree._Element) -> bytes:
    written: bytes = etree.tostring(
        element, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    return written
