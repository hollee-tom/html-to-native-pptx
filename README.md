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

### What it gets right that others often don't

- **See-through colours.** A faint tint behind text stays a faint tint, and an element's
  `opacity` carries through, because PowerPoint has no group opacity of its own.
- **Borders on some sides.** A rule above a card stays a rule. It isn't drawn as a box around
  the whole card.
- **Badges and highlighted words** keep their background, including in table cells, and the
  paragraph stays one editable paragraph.
- **Spacing between inline pieces.** "01" and "Agenda" set apart with margin stay apart.
- **Content in empty-looking wrappers.** A wrapper with no height of its own, whose children are
  positioned freely, still has its children exported.
- **No surprise styling from PowerPoint.** Shapes don't pick up the theme's shadow, and tables
  don't pick up PowerPoint's default grid lines.
- **Odd input doesn't break the file.** A chart with no rows is skipped, and an absurd `colspan`
  is capped.

## Fonts

By default, the fonts your page uses are embedded in the `.pptx`. The slides then look right
on a computer that doesn't have those fonts installed. Turn this off with `--no-embed-fonts`.

- **It uses the fonts your page loaded**, wherever they came from: a font service such as
  Google Fonts, a CDN, or local files. There's nothing to configure.
- **Each piece of text gets the exact font file the browser used**, named the way PowerPoint
  expects. For example, a 300 weight becomes "Inter Light", so PowerPoint finds it.
- **Variable fonts work.** Many viewers draw a variable font at its default weight, which is
  often the boldest. So each weight your slides use is saved as its own fixed font.
- **Font licences are respected.** A font that doesn't allow embedding is named in the file but
  not included.
- **Not yet checked in PowerPoint.** Embedded fonts have been verified in LibreOffice. PowerPoint,
  Keynote and Google Slides haven't been tested yet.

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

We compared html-to-native-pptx with four other open-source HTML-to-PowerPoint converters on 193
real slides, then on a public test deck anyone can rerun.

**What it shows**

- **Closest to the original.** Its slides look the most like the HTML of the five tools.
- **No lost text.** It kept every word. The other tools lost or ran together 60 to 408 words.
- **Most stays editable.** Tables stay real PowerPoint tables, borders stay lines, and charts stay
  charts. Other tools turn some of these into pictures or plain text.
- **Your fonts come with the file.** It embeds the deck's own fonts, so slides look right on a
  computer that doesn't have them installed.

**How much to trust it**

- The slides were checked by opening them in LibreOffice, not PowerPoint. PowerPoint may wrap a
  line or space a letter slightly differently. We haven't yet tested opening the files in
  PowerPoint, Keynote or Google Slides.
- The 193 real slides all came from one product's decks. HTML written another way may use CSS
  these decks don't, so check your own slides.
- Each tool was run once. Small differences, about half a point on the visual score, are noise.

### On 193 real slides

These are 8 private decks, so only the totals are published.

| | **html-to-native-pptx** | dom-to-pptx | SlideSmith | html-to-pptx | html-to-editable-pptx |
|---|---|---|---|---|---|
| Visual difference from the HTML (lower is better) | **5.2** | 6.2 | 7.3 | 7.4 | 8.2 |
| Slides that look clearly different | **3** | **3** | 10 | 4 | 12 |
| Words lost or run together (of 24,508) | **0** | 90 | 90 | 146 | 558 |
| Tables kept as tables (of 116) | **116** | **116** | **116** | 0 | 0 |
| Parts turned into pictures (fewer is more editable) | **184** | 359 | 359 | **184** | **184** |
| Letter-spacing kept | **100%** | **100%** | **100%** | 97% | 97% |
| See-through colours kept | **99%** | **99%** | **99%** | 0% | 0% |
| Rotated elements kept | 96% | **100%** | 96% | **100%** | 91% |

The visual difference is the average grey-level difference per pixel between the HTML and the
PowerPoint slide, on a 0 to 255 scale. A slide counts as clearly different above 15.

### On the public test deck

`corpus/deck.html` is 21 slides of original HTML, built to recreate the hard cases found in real
decks: badges and highlights, see-through colours, rotation, letter-spacing, one-sided borders,
gradient headings, photo backgrounds with overlays, charts and web fonts. Its fonts are openly
licensed and their licences are in `corpus/fonts/`.

| | **html-to-native-pptx** | dom-to-pptx |
|---|---|---|
| Visual difference from the HTML (lower is better) | **4.6** | 9.3 |
| Letters lost (of 1,998) | **0** | **0** |
| Charts kept as charts (of 5) | **5** | 0 |
| One-sided borders kept as lines (of 8) | **8** | 0 |
| Fonts embedded | **Yes** | No |
| Rotated elements kept (of 5) | 3 | **5** |

dom-to-pptx also dropped the full-slide background photo on one slide. Our two rotation misses
are badges rotated inside a line of text, listed under Known gaps.

To rerun it yourself (needs Docker):

```sh
benchmark/run.sh                                            # html-to-native-pptx only
benchmark/run.sh --tools html-to-native-pptx,dom-to-pptx    # with dom-to-pptx too
```

Results go to `benchmark/out/results.md`. dom-to-pptx is installed and run only inside the
container.

## Development

Everything that needs a browser or LibreOffice runs in Docker so it is the same everywhere:

```sh
docker/dev.sh pytest -q          # tests (a Chromium is required for the end-to-end ones)
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Licence

MIT, copyright hollee-tom. Fonts in `corpus/fonts/` are SIL OFL 1.1 (licences alongside).
