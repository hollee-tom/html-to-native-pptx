"""Runs the open-source dom-to-pptx on the same HTML, so the scorers can compare it.

dom-to-pptx is a browser library: it is injected into the page and exports the slide elements.
Its code is third-party and untrusted, so this adapter runs only inside the benchmark's Docker
container, where `npm install dom-to-pptx` has put it under NODE_PATH's `node_modules`.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUNDLE = (
    Path(os.environ.get("DOM_TO_PPTX_DIR", "/opt/dom-to-pptx"))
    / "node_modules/dom-to-pptx/dist/dom-to-pptx.bundle.js"
)
EXPORT = """async (options) => {
  const slides = [...document.querySelectorAll(options.selector)];
  const blob = await window.domToPptx.exportToPptx(slides, { skipDownload: true, fileName: "x.pptx", width: options.width / 96, height: options.height / 96 });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(text);
}"""


def main(html: str, out: str, selector: str, width: int, height: int) -> None:
    """Export `html`'s slides with dom-to-pptx into `out`."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("NATIVEDECK_CHROMIUM"))
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(Path(html).resolve().as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.add_script_tag(path=str(BUNDLE))
        Path(out).write_bytes(
            base64.b64decode(
                page.evaluate(EXPORT, {"selector": selector, "width": width, "height": height})
            )
        )
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
