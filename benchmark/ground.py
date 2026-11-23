"""Ground truth: Chromium lays the HTML out once, and everything the scorers compare against is
recorded from that layout: where each text sits, which CSS features each slide uses and where,
and a screenshot of every slide."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

FEATURES_JS = r"""(selector) => {
const num = (v) => parseFloat(v) || 0;
const rgba = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null;
  const p = m[1].split(/[ ,\/]+/).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
const all = [...document.querySelectorAll(selector)];
const slides = all.filter((el) => !all.some((o) => o !== el && o.contains(el)));
return slides.map((slide) => {
  const origin = slide.getBoundingClientRect();
  const R = (e) => { const b = e.getBoundingClientRect(); return [b.x - origin.x, b.y - origin.y, b.width, b.height]; };
  const feats = []; const texts = [];
  slide.querySelectorAll("*").forEach((e) => {
    if (e.closest("svg") && e.tagName !== "svg") return;
    const cs = getComputedStyle(e);
    if (cs.display === "none" || cs.visibility === "hidden") return;
    const r = R(e);
    if (r[2] <= 0 || r[3] <= 0) return;
    const own = [...e.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
    const txt = (e.innerText || "").trim().slice(0, 40);
    if (own.length && !e.closest("table[data-chart-data]")) {
      const range = document.createRange();
      let box = null;
      for (const n of own) {
        range.selectNodeContents(n);
        const b = range.getBoundingClientRect();
        box = box ? [Math.min(box[0], b.left), Math.min(box[1], b.top), Math.max(box[2], b.right), Math.max(box[3], b.bottom)] : [b.left, b.top, b.right, b.bottom];
      }
      texts.push({ t: own.map((n) => n.textContent).join(" "), x: box[0] - origin.x, y: box[1] - origin.y, w: box[2] - box[0], h: box[3] - box[1], svg: false });
    }
    const bg = rgba(cs.backgroundColor);
    if (bg && bg[3] > 0.3 && own.length && r[2] * r[3] < 0.15 * origin.width * origin.height && r[3] < 80 && cs.backgroundClip !== "text")
      feats.push({ k: "chip", r, txt, bg });
    if (num(cs.opacity) < 1 && txt) feats.push({ k: "opacity", r, txt, op: num(cs.opacity), col: rgba(cs.color) });
    if (cs.transform !== "none") {
      const m = cs.transform.match(/matrix\(([^)]+)\)/);
      if (m) { const p = m[1].split(",").map(Number); const ang = Math.atan2(p[1], p[0]) * 180 / Math.PI;
        if (Math.abs(ang) > 0.5 && r[2] * r[3] > 50) feats.push({ k: "rot", r, txt, ang: Math.round(ang * 10) / 10 }); }
    }
    if (cs.letterSpacing !== "normal" && num(cs.letterSpacing) !== 0 && own.length) feats.push({ k: "ls", r, txt, ls: num(cs.letterSpacing) });
    if ((cs.webkitBackgroundClip === "text" || cs.backgroundClip === "text") && txt) feats.push({ k: "gradtext", r, txt });
    const sides = ["Top", "Right", "Bottom", "Left"];
    const b = sides.map((s) => ({ w: num(cs["border" + s + "Width"]), c: rgba(cs["border" + s + "Color"]), st: cs["border" + s + "Style"] }));
    const vis = b.map((x) => x.w > 0 && x.st !== "none" && x.c && x.c[3] > 0);
    const n = vis.filter(Boolean).length;
    if (n >= 1 && n <= 3 && e.tagName !== "TD" && e.tagName !== "TH") feats.push({ k: "pborder", r, txt, sides: vis, w: b.map((x) => x.w) });
    if (e.tagName === "TABLE" && !e.hasAttribute("data-chart-data")) feats.push({ k: "table", r, txt });
    if (e.tagName === "svg" && r[2] * r[3] > 400) { feats.push({ k: "svg", r, txt: "" }); }
    if (e.tagName === "IMG") feats.push({ k: "img", r, txt: "" });
    if (e.tagName === "FIGURE" && e.hasAttribute("data-chart")) feats.push({ k: "chart", r, txt: "" });
  });
  return { feats, texts };
});
}"""


def record(html: Path, out: Path, selector: str, width: int, height: int) -> tuple[Any, int]:
    """Write `ground.json` (texts and features per slide) and `shots/sNN.png` into `out`.

    Returns the per-slide records and the slide count. The browser is Playwright's own, as the
    package under test uses.
    """
    (out / "shots").mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("NATIVEDECK_CHROMIUM"))
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(html.resolve().as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
        found = page.evaluate(FEATURES_JS, selector)
        slides = page.locator(selector)
        for number in range(slides.count()):
            slides.nth(number).screenshot(path=str(out / "shots" / f"s{number + 1:02d}.png"))
        browser.close()
    (out / "ground.json").write_text(json.dumps(found))
    return found, len(found)
