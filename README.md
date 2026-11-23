# html-to-native-pptx

**High-fidelity HTML to native, editable PowerPoint.**

html-to-native-pptx opens a deck of HTML slides in Chromium, measures what the browser actually drew, and
writes a `.pptx` whose contents are real PowerPoint objects:

- **Text** stays text: text boxes with runs, fonts, sizes, colours, letter-spacing, bullets,
  links, super/subscript, and inline chips and marked words as run highlights.
- **Tables** stay tables: native tables with merged cells, fills and per-side borders.
- **Shapes** stay shapes: rectangles, rounded rectangles, ellipses and lines, with fill, outline,
  opacity and rotation.
- **Charts** stay charts: figures that follow a small markup format become native PowerPoint
  charts with editable data ([format](docs/charts.md)).
- **Pictures are only a fallback**, for what PowerPoint cannot express (a gradient, an SVG, a
  photograph, a `::before` decoration). Each is a transparent picture of just that element,
  placed *behind* the native text, so the text on top is still yours to edit.

It is not a slide-screenshot exporter: a deck made of one picture per slide is not "native".

## Quick start

```sh
pip install html-to-native-pptx
playwright install chromium
html-to-native-pptx deck.html -o deck.pptx
```

```python
from pathlib import Path
from html_to_native_pptx import convert

convert(Path("deck.html"), Path("deck.pptx"), slide_selector="section", width=1280, height=720)
```

`html` may be a `Path` to a file, or a string of markup (pass `base_dir=` so its relative links
resolve). Every element matching `slide_selector` is one slide of `width` x `height` CSS pixels.

```text
html-to-native-pptx deck.html -o deck.pptx
    -s, --slide-selector SELECTOR   CSS selector of one slide (default: section)
        --width / --height PX       slide size in CSS pixels (default: 1280x720)
        --no-embed-fonts            name fonts only; do not embed them
        --no-freeze-animations      measure animations as they stand
        --chromium PATH             a Chromium binary to drive (or set HTML_TO_NATIVE_PPTX_CHROMIUM)
        --timeout SECONDS           how long to wait on the page (default: 60)
```

`html_to_native_pptx.measure(...)` returns the measurements (a pydantic `MeasuredDeck`) without writing a
file, and `html_to_native_pptx.deck_pptx(deck)` writes one from measurements, with no browser needed.

## How it works

1. **Measure in the browser.** Playwright loads the page as a browser does (scripts run, images
   and fonts load from wherever they point). A script walks each slide's DOM and records, from
   computed styles and layout, every text run, table, chart, shape and picture, in slide pixels.
2. **Capture pictures.** Each element PowerPoint cannot express is screenshot on its own with
   everything else hidden, over a transparent background. Elements with a background image or
   gradient are shot with their text made clear, so the text can stay native on top.
3. **Write natively.** python-pptx writes the objects at the measured positions. Small, targeted
   XML edits cover what it lacks: alpha, highlights, the "No Style, No Grid" table style,
   explicit no-line cell sides, and embedded fonts.

Code layout: `pages.py` (loading), `assets/measure.js` (the in-browser measurer),
`measurer.py` (drives it and takes the pictures), `model.py` (the measured-deck contract),
`fontfiles.py` and `fonts.py` (font discovery and embedding), `writer/` (one module each for
text, shapes, tables, charts, pictures, plus colour and units), `convert.py` and `cli.py`.

### Why it is built this way

- **Opacity is folded into colour alpha.** PowerPoint has no group opacity, so an element's
  `opacity`, and its ancestors', is multiplied into every fill, line and text colour as alpha.
- **A border on only some sides is drawn as strips.** A card with a rule above it used to export
  with that colour as an outline around the whole box. A border alike on every side is an
  outline; otherwise each bordered side is a thin filled strip behind the text, drawn over the
  box's fill.
- **See-through colours stay see-through.** `rgba(35,31,32,.08)` behind dark text is kept as an
  alpha colour; measured as solid, the box came out the colour of its text.
- **Boxless wrappers are not skipped.** A wrapper with zero height whose children are all
  positioned paints nothing, but its children are still measured.
- **Inline backgrounds are run highlights.** A chip or marked word keeps its paragraph whole,
  and status chips in table cells keep their fill.
- **Inline margins, borders and padding become spaced no-break spaces,** so `01` and `Agenda`
  do not run together. Spaces collapse across runs as the browser collapses them.
- **Shapes carry no theme style.** python-pptx gives every shape a style pointing at a theme
  shadow; a viewer that draws it darkens a see-through overlay on a photo by about 20 grey
  levels, so the style is removed.
- **Tables carry no default grid.** A cell writes only the sides the page borders; every bare
  side is an explicit no line, and the table uses PowerPoint's "No Style, No Grid" style.
- **Spans are capped.** A `colspan` of 1000 would be a thousand empty columns; spans stop at the
  widest row's cells and PowerPoint's 75-column limit.
- **A chart without rows draws no chart**, as the page does; an axis whose minimum is
  not below its maximum drops both bounds, which PowerPoint would repair away.

## Fonts

By default the fonts your page loaded are embedded in the `.pptx`, so it opens in the right
typeface on a machine that lacks them (`--no-embed-fonts` turns this off).

- **No font map.** Font bytes come from what the browser fetched: every font response is kept,
  so a font service, a CDN, a `file://` path or a `data:` URL all work as the page uses them.
- **Runs are matched to the face the browser drew.** CSS font matching picks it (same style,
  then nearest weight, lighter first up to 500 and heavier above; where several files share a
  family and weight, as a font service's per-script subsets do, the one holding the run's
  characters). Each run is then named by the family *inside* that file, which is what
  PowerPoint matches and differs from the CSS family for most weights ("Fraunces" at 300 is a
  family called "Fraunces Light").
- **Variable fonts are cut per weight.** PowerPoint and most other viewers draw a variable file
  at its default weight, which for many fonts is the heaviest, making every run extra bold. So
  each weight a run uses is cut out as a fixed font and named as PowerPoint names weights
  ("Inter" for 400 and 700, "Inter Light" for 300).
- **Licences are respected.** A face whose OS/2 `fsType` forbids embedding is named, not carried.
- **Format.** PowerPoint stores embedded fonts as uncompressed Embedded OpenType (`.fntdata`);
  PostScript (CFF) outlines, as most `.otf` files have, are converted to TrueType first. A
  family name holds four slots (regular, bold, italic, bold italic), so a name with more faces
  than that keeps the first.
- **Not verified in PowerPoint.** The files open in LibreOffice and python-pptx; embedded-font
  rendering in desktop PowerPoint, Keynote and Google Slides has not been tested.

## Supported CSS and markup

Text: font family, size, weight, style, colour, `letter-spacing`, `text-transform`,
`text-align`, `line-height`, underline, strike-through, `vertical-align: super/sub`, links,
`<br>`, `<ul>`/`<ol>` with nesting, blockquotes and `<cite>`. Inline elements with a background,
margin, padding or border become highlights and gaps. Gradient-clipped text
(`background-clip: text`) stays editable.

Boxes: background colour (with alpha), border (all sides, or per side), `border-radius`, `opacity`
(own and inherited), 2D `transform: rotate()` and scale, absolutely positioned and zero-height
wrappers, flex and grid layouts (anything the browser lays out is measured where it landed),
full-slide background images and translucent overlays. `data-shape="ellipse|line|rect"` hints a
plain shape.

Tables: `colspan`, `rowspan`, cell fills, per-side borders, vertical alignment, captions.

Charts: `figure[data-chart]` with a `table[data-chart-data]`, see [docs/charts.md](docs/charts.md).

Pictures (fallback): `<img>`, inline `<svg>`, elements with `background-image` or a gradient,
and elements with `::before`/`::after` content.

## Known gaps

- **Inline rotated badges.** A rotated `inline-block` inside a line of text is flattened into the
  paragraph: its rotation and border are lost (a rotated *block* is fine).
- **Dashed and dotted borders** are drawn solid.
- **Box shadows** are not drawn.
- **Pseudo-elements that paint outside their element's box** are clipped to the box when
  pictured.
- **Hyperlinks** take the presentation theme's link colour in PowerPoint and LibreOffice, not the
  CSS colour.
- **Gradient-clipped text** is editable, but the gradient lives in the picture behind it and the
  native text on top is clear; edited text does not change the picture.
- **Pictures are 1x** device pixels, so a pictured photograph is as sharp as the page showed it.
- **3D transforms, filters, `mix-blend-mode`, `clip-path`** are not represented.
- **Line breaks can differ** where PowerPoint's text layout differs from the browser's; text
  that the browser set on one line is kept on one line.
- **PowerPoint itself is untested**; see Fonts and the benchmark notes.

## Benchmark

Two benchmarks, kept separate. Both use the same scorers: letters and digits kept, where text
sits, how many native objects of each kind the file holds, a per-feature check (does each CSS
feature have a PowerPoint equivalent?), and a visual check, in which LibreOffice draws the PPTX
and each page is compared with Chromium's screenshot of the HTML slide as mean absolute grey
difference at 640x360 (lower is better). **LibreOffice stands in for PowerPoint.** It differs in
line breaking, font fallback, variable fonts and highlight rendering, so visual numbers are
indicative only. One run each, no confidence intervals; treat MAE differences below about 0.5 as
noise.

### Synthetic public corpus (reproducible)

`corpus/deck.html` is 21 slides of original HTML (no third-party or client content) recreating
the difficulties found in real decks: inline chips and badges (also inside table cells),
opacity on text and shapes, rotated cards, letter-spaced labels and inline margins, partial
borders and tables with borders on some sides, gradient-clipped headings and
`::before`/`::after`, zero-height wrappers with positioned children, a full-slide photo with a
translucent overlay, native charts, and fonts: Inter (variable), DM Serif Display and IBM Plex
Mono (static), all SIL OFL, with their licences in `corpus/fonts/`. Pictures are drawn by
`corpus/make_images.py`.

Rerun it (Docker; Chromium, LibreOffice and poppler come from the image):

```sh
benchmark/run.sh                          # html-to-native-pptx only
benchmark/run.sh --tools html-to-native-pptx,dom-to-pptx   # also compare dom-to-pptx
```

`dom-to-pptx` is third-party code, so `npm install dom-to-pptx` and the run happen only inside
the container. Results go to `benchmark/out/results.{json,md}`.

Results on 2026-11-23 (LibreOffice 24.2, Chromium from Playwright 1.65, 21 slides, 1280x720):

| | html-to-native-pptx | dom-to-pptx |
|---|---|---|
| Slides written / LibreOffice pages | 21 / 21 | 21 / 21 |
| Letters and digits missing / extra (of 1998) | 0 / 0 | 0 / 0 |
| Text blocks outside their box | 4 of 123 | 2 of 123 |
| Native text boxes / shapes | 116 / 31 | 131 / 47 |
| Native tables / charts | 2 / 5 | 2 / 0 |
| Pictures | 7 | 15 |
| Embedded font parts | 10 | 0 |
| Pixel MAE mean (lower is better) | 4.56 | 9.29 |
| Slides with MAE over 15 | 1 | 2 |
| Feature: charts native | 5/5 | 0/5 |
| Feature: chips | 6/6 | 6/6 |
| Feature: letter-spacing | 32/32 | 32/32 |
| Feature: opacity | 3/3 | 3/3 |
| Feature: partial borders as strips | 8/8 | 0/8 |
| Feature: rotation | 3/5 | 5/5 |
| Feature: tables native | 2/2 | 2/2 |
| Feature: `<img>` as picture | 1/1 | 0/1 |

Reading it:

- html-to-native-pptx's slides above MAE 8 are chart slides 10 to 12 (the page's own SVG drawing against a
  native PowerPoint chart, which look different on purpose) and slide 13 (variable-weight text).
- dom-to-pptx lost the full-slide CSS background photo on slide 8 (MAE 116) and draws partial
  borders as pictures or not at all. It was run with default options.
- html-to-native-pptx's two rotation misses are the two inline rotated badges listed under Known gaps.
- Conversion time is not comparable: html-to-native-pptx's includes cutting and embedding fonts.

### Private corpus (numbers only)

Before this package existed, the engine it was extracted from was benchmarked on **a private
corpus of 8 real generated decks (193 slides, 1280x720)**. Those decks are not published and
nothing from them is in this repository; only these aggregates are. Same scorers as above, all
tools re-scored with the same scripts; fonts were installed for LibreOffice for every tool alike.

| | engine before the fixes | **html-to-native-pptx engine** | dom-to-pptx | html_to_pptx | slidesmith | editable-pptx |
|---|---|---|---|---|---|---|
| Slides exported | 193 | 193 | 193 | 193 | 193 | 193 |
| Words missing / extra (of 24508) | 60 / 30 | **0 / 0** | 60 / 30 | 104 / 42 | 60 / 30 | 408 / 150 |
| Native text boxes | 1853 | 1853 | 1859 | 6310 | 1851 | 1860 |
| Native tables | 116 | 116 | 116 | 0 | 116 | 0 |
| Pictures | 184 | 184 | 359 | 184 | 359 | 184 |
| Embedded font parts | 0 | 21 | 27 | 0 | 24 | 12 |
| Pixel MAE mean | 6.33 | **5.23** | 6.24 | 7.44 | 7.34 | 8.20 |
| Slides with MAE over 15 | 8 | 3 | 3 | 4 | 10 | 12 |
| Letter-spacing kept | 0% | 100% | 100% | 97% | 100% | 97% |
| Opacity kept | 0% | 99% | 99% | 0% | 99% | 0% |
| Inline chips kept (incl. highlights) | 83% | 100% | 100% | 81% | 80% | 96% |
| Partial borders as strips | 100% | 100% | 23% | 100% | 23% | 100% |
| Rotation kept | 67% | 96% | 100% | 100% | 96% | 91% |

Caveats: eight decks from one product and one run each; no real PowerPoint, Keynote or Google
Slides rendering; the "engine before the fixes" column is how the same code performed before
the round of fixes now in this package; the fonts of one deck loaded over the network were
unavailable to the offline html-to-native-pptx run, inflating its placement error on that deck; and
LibreOffice drew one embedded variable font heavier than the HTML, which hurts two decks and
may not occur in PowerPoint. Opening and repair behaviour in real PowerPoint is untested.

## Development

Everything that needs a browser or LibreOffice runs in Docker so it is the same everywhere:

```sh
docker/dev.sh pytest -q          # tests (a Chromium is required for the end-to-end ones)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Licence

MIT, copyright hollee-tom. Fonts in `corpus/fonts/` are SIL OFL 1.1 (licences alongside).
