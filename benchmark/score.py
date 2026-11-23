"""Scoring a PPTX against the ground truth: words kept, where text sits, what kinds of objects
the file holds, and whether each CSS feature has a PowerPoint equivalent."""

from __future__ import annotations

import collections
import re
import statistics
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree
from pptx import Presentation

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
SLACK = 6
"""Pixels of tolerance when asking whether a text block's centre lies inside a PPTX box."""


def words(text: str) -> list[str]:
    """The lower-case words of `text`."""
    return re.findall(r"\w+", text.lower())


def flat(prs: Any, canvas: int) -> list[list[dict[str, Any]]]:
    """Every shape of every slide in canvas pixels, with the fill, alpha, rotation and text the
    checks need; group shapes are opened."""
    scale = canvas / prs.slide_width
    slides: list[list[dict[str, Any]]] = []
    for slide in prs.slides:
        found: list[dict[str, Any]] = []

        def walk(shapes: Any, found: list[dict[str, Any]] = found) -> None:
            for shape in shapes:
                if shape.shape_type == 6:
                    walk(shape.shapes)
                    continue
                element = shape._element
                table = bool(getattr(shape, "has_table", False) and shape.has_table)
                item: dict[str, Any] = {
                    "x": (shape.left or 0) * scale,
                    "y": (shape.top or 0) * scale,
                    "w": (shape.width or 0) * scale,
                    "h": (shape.height or 0) * scale,
                    "pic": element.tag.endswith("}pic"),
                    "tbl": table,
                    "chart": bool(getattr(shape, "has_chart", False) and shape.has_chart),
                    "rot": float(getattr(shape, "rotation", 0) or 0),
                    "text": "",
                    "el": element,
                    "fill": None,
                    "alpha": 1.0,
                    "grad": False,
                }
                properties = element.find(".//p:spPr", NS)
                if properties is not None:
                    solid = properties.find("a:solidFill/a:srgbClr", NS)
                    if solid is not None:
                        item["fill"] = solid.get("val")
                        alpha = solid.find("a:alpha", NS)
                        if alpha is not None:
                            item["alpha"] = int(alpha.get("val")) / 100000
                    item["grad"] = properties.find("a:gradFill", NS) is not None
                if getattr(shape, "has_text_frame", False):
                    item["text"] = shape.text_frame.text
                if table:
                    item["text"] = " ".join(c.text for r in shape.table.rows for c in r.cells)
                found.append(item)

        walk(slide.shapes)
        slides.append(found)
    return slides


def structure(path: Path, ground: list[dict[str, Any]], canvas: int) -> dict[str, Any]:
    """Word loss, text placement error and object counts for one file."""
    prs = Presentation(str(path))
    shapes = flat(prs, canvas)
    result: dict[str, Any] = {
        "slides": len(prs.slides),
        "words_expected": 0,
        "words_missing": 0,
        "words_extra": 0,
        "native_text_boxes": 0,
        "native_shapes": 0,
        "native_tables": 0,
        "native_charts": 0,
        "pictures": 0,
        "full_slide_pictures": 0,
    }
    errors: list[float] = []
    outside = checked = 0
    for number, found in enumerate(shapes):
        boxes: list[tuple[float, float, float, float, str]] = []
        written: list[str] = []
        for item in found:
            if item["pic"]:
                result["pictures"] += 1
                result["full_slide_pictures"] += item["w"] * item["h"] > 0.6 * canvas * canvas * prs.slide_height / prs.slide_width
            elif item["chart"]:
                result["native_charts"] += 1
            elif item["tbl"]:
                result["native_tables"] += 1
            elif item["text"].strip():
                result["native_text_boxes"] += 1
            else:
                result["native_shapes"] += 1
            if item["text"].strip():
                written.append(item["text"])
                boxes.append((item["x"], item["y"], item["w"], item["h"], item["text"].lower()))
        texts = ground[number]["texts"] if number < len(ground) else []
        have = collections.Counter(words(" ".join(written)))
        want = collections.Counter(words(" ".join(t["t"] for t in texts)))
        result["words_expected"] += sum(want.values())
        result["words_missing"] += sum((want - have).values())
        result["words_extra"] += sum((have - want).values())
        tables = [f["r"] for f in ground[number]["feats"] if f["k"] == "table"]
        for text in texts:
            first = words(text["t"])
            cx, cy = text["x"] + text["w"] / 2, text["y"] + text["h"] / 2
            if not first or any(
                r[0] <= cx <= r[0] + r[2] and r[1] <= cy <= r[1] + r[3] for r in tables
            ):
                continue
            checked += 1
            near = [b for b in boxes if first[0] in b[4]]
            if not any(
                b[0] - SLACK <= cx <= b[0] + b[2] + SLACK and b[1] - SLACK <= cy <= b[1] + b[3] + SLACK
                for b in near
            ):
                outside += 1
            if near:
                errors.append(
                    min(
                        min(
                            ((b[0] - text["x"]) ** 2 + (b[1] - text["y"]) ** 2) ** 0.5,
                            ((b[0] + b[2] / 2 - cx) ** 2 + (b[1] + b[3] / 2 - cy) ** 2) ** 0.5,
                        )
                        for b in near
                    )
                )
    errors.sort()
    result["text_blocks_checked"] = checked
    result["text_blocks_outside_source_box"] = outside
    result["placement_median_px"] = round(statistics.median(errors), 1) if errors else None
    result["placement_p90_px"] = round(errors[int(len(errors) * 0.9)], 1) if errors else None
    with zipfile.ZipFile(path) as package:
        result["embedded_font_parts"] = sum(
            1 for name in package.namelist() if name.startswith("ppt/fonts/") and not name.endswith(".rels")
        )
    return result


def _overlap(a: dict[str, Any], r: list[float]) -> tuple[float, float]:
    """Intersection over union of a shape and a rectangle, and the share of the rectangle covered."""
    x1, y1 = max(a["x"], r[0]), max(a["y"], r[1])
    x2, y2 = min(a["x"] + a["w"], r[0] + r[2]), min(a["y"] + a["h"], r[1] + r[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["w"] * a["h"] + r[2] * r[3] - inter
    return (inter / union if union else 0, inter / (r[2] * r[3]) if r[2] * r[3] else 0)


def _norm(text: str) -> str:
    """Words joined by single spaces, for finding a text inside a shape's text."""
    return " ".join(words(text))


def _close(a: tuple[int, ...], b: list[float], tolerance: int = 45) -> bool:
    """Whether two colours are within `tolerance` on every channel."""
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=False))


def features(path: Path, ground: list[dict[str, Any]], canvas: int) -> dict[str, list[int]]:
    """For each CSS feature the HTML uses, `[passed, total]`: does the PPTX hold an equivalent?

    chip: a filled shape or a run highlight of the right colour over each inline badge.
    opacity: alpha in a colour, or a changed colour. rot: a shape turned by the same angle.
    ls: a run spacing matching the letter-spacing. pborder: a thin strip on each bordered side.
    table, chart: a native table or chart at that place. img: a picture over each image.
    gradtext: the heading is native text. svg: a picture over each drawing.
    """
    shapes = flat(Presentation(str(path)), canvas)
    counts: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for number, slide in enumerate(ground):
        have = shapes[number] if number < len(shapes) else []
        tables = [f["r"] for f in slide["feats"] if f["k"] == "table"]
        for feat in slide["feats"]:
            kind, r = feat["k"], feat["r"]
            text = _norm(feat.get("txt", ""))
            if kind in ("chip", "pborder") and any(
                t[0] - 2 <= r[0] + r[2] / 2 <= t[0] + t[2] + 2 and t[1] - 2 <= r[1] + r[3] / 2 <= t[1] + t[3] + 2
                for t in tables
            ):
                continue
            ok = False
            if kind == "chip":
                ok = any(
                    s["fill"] and not s["pic"] and _overlap(s, r)[0] > 0.5
                    and _close(_rgb(s["fill"]), feat["bg"][:3])
                    for s in have
                ) or any(
                    text[:10] in _norm(s["text"]) and _highlight(s["el"], feat["bg"][:3]) for s in have if s["text"]
                )
            elif kind == "opacity":
                ok = any(_faded(s["el"], s["alpha"], feat["col"]) for s in have if s["text"] and text[:12] in _norm(s["text"]))
            elif kind == "rot":
                ok = any(
                    abs((s["rot"] - feat["ang"] + 180) % 360 - 180) < 3
                    for s in have
                    if _overlap(s, r)[1] > 0.3 or (text and text[:10] in _norm(s["text"]))
                )
            elif kind == "ls":
                ok = any(
                    _spaced(s["el"], feat["ls"]) for s in have if s["text"] and text[:10] in _norm(s["text"])
                )
            elif kind == "pborder":
                ok = all(_strip(have, r, side, wd) for side, on, wd in zip("TRBL", feat["sides"], feat["w"], strict=True) if on)
            elif kind == "table":
                ok = any(s["tbl"] and abs(s["x"] - r[0]) < 8 and abs(s["y"] - r[1]) < 8 for s in have)
            elif kind == "chart":
                ok = any(s["chart"] and _overlap(s, r)[0] > 0.3 for s in have)
            elif kind in ("img", "svg"):
                ok = any(s["pic"] and _overlap(s, r)[0] > 0.4 for s in have)
            elif kind == "gradtext":
                ok = any(s["text"] and text[:10] in _norm(s["text"]) for s in have)
            else:
                continue
            counts[kind][1] += 1
            counts[kind][0] += ok
    return dict(counts)


def _rgb(value: str) -> tuple[int, ...]:
    """A `rrggbb` string as three channels."""
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _highlight(element: Any, colour: list[float]) -> bool:
    """Whether a shape holds a run highlight of about this colour."""
    return any(
        _close(_rgb(h.get("val")), colour) for h in element.iterfind(".//a:highlight/a:srgbClr", NS)
    )


def _faded(element: Any, alpha: float, colour: list[float] | None) -> bool:
    """Whether a shape carries alpha, or a text colour other than the element's own."""
    xml = etree.tostring(element).decode()
    if "<a:alpha" in xml or alpha < 1:
        return True
    found = re.search(r'<a:rPr[^>]*>.*?<a:srgbClr val="([0-9A-Fa-f]{6})"', xml, re.S)
    return bool(found and colour and not _close(_rgb(found.group(1)), colour[:3], 10))


def _spaced(element: Any, spacing: float) -> bool:
    """Whether a run's `spc` (hundredths of a point) matches the letter-spacing in pixels."""
    return any(
        abs(int(v) / 100 * 96 / 72 - spacing) < max(0.6, abs(spacing) * 0.35)
        for v in re.findall(r'spc="(-?\d+)"', etree.tostring(element).decode())
    )


def _strip(have: list[dict[str, Any]], r: list[float], side: str, width: float) -> bool:
    """Whether a thin non-picture shape lies along one side of the rectangle `r`."""
    for s in have:
        if s["pic"]:
            continue
        horizontal = side in "TB" and s["h"] <= width * 2 + 3 and s["w"] >= r[2] * 0.5
        vertical = side in "LR" and s["w"] <= width * 2 + 3 and s["h"] >= r[3] * 0.5
        if (horizontal or vertical) and (
            r[0] - 4 <= s["x"] + s["w"] / 2 <= r[0] + r[2] + 4 and r[1] - 4 <= s["y"] + s["h"] / 2 <= r[1] + r[3] + 4
        ):
            return True
    return False
