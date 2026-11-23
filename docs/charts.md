# Native charts: the `figure[data-chart]` format

nativedeck turns a figure into a real PowerPoint chart (editable data, colours, legend) when it
follows this opt-in format. Charts are not detected from SVG, canvas or charting libraries: the
page says what the chart is, in markup, and nativedeck reads those numbers.

```html
<figure data-chart="column" data-legend="bottom" data-labels="on" data-format="currency:USD"
        style="--chart-1:#2f5bea; --chart-2:#e8590c">
  <figcaption>Revenue by quarter</figcaption>
  <div data-chart-drawing>… your own drawing of the chart (SVG, canvas, a library) …</div>
  <table data-chart-data>
    <thead><tr><th></th><th>2024</th><th>2025</th></tr></thead>
    <tbody>
      <tr><td>Q1</td><td>12</td><td>15</td></tr>
      <tr><td>Q2</td><td>18</td><td>21</td></tr>
    </tbody>
  </table>
</figure>
```

## Parts

| Part | Meaning |
|---|---|
| `figure[data-chart]` | The chart. The value is its kind (below). |
| `table[data-chart-data]` | Direct child of the figure. The first header cell is empty; the other header cells name the series. The first cell of each body row is the category; the other cells are numbers (empty for no value). It may be hidden with `display:none`. |
| `figcaption` | Optional. Written as a native text box above the chart. |
| `[data-chart-drawing]` | Optional direct child: what the page draws for the chart. Its box is where the native chart is placed. Without it, the figure's box below the caption is used. |

## Kinds

`bar`, `bar-stacked`, `column`, `column-stacked`, `line`, `area`, `pie`, `donut`, `scatter`
(first series is x, the rest are y), `combo` (first series as columns, the others as lines on
the same axes), `waterfall` (one series of changes, drawn as floating columns), `funnel`
(one series, sorted descending), `gauge` (one value on a half ring between the axis bounds).
`pie`, `donut`, `waterfall`, `funnel` and `gauge` use only the first series.

## Attributes on the figure

| Attribute | Values | Default |
|---|---|---|
| `data-legend` | `top`, `bottom`, `right`, `none` | `bottom` |
| `data-labels` | `on` shows value labels | off |
| `data-format` | `number`, `percent` (values are already percentages: 45 is 45%), `currency:USD` / `GBP` / `EUR` / `JPY` (or any code, shown as a suffix) | `number` |
| `data-axis-min`, `data-axis-max` | numbers. If the minimum is not below the maximum, both are dropped, because PowerPoint would repair the chart away. | automatic |

## Colours and text

Series colours come from the CSS custom properties `--chart-1` … `--chart-6`, read from the
figure and then from its slide. Without them a built-in palette is used. The chart's text takes
the figure's computed colour, font family and size.

## Behaviour worth knowing

- A chart with no rows or no series is skipped, as the page would draw none either.
- Whole-number data prints without a trailing decimal point.
- Everything inside the figure other than its caption is replaced by the native chart: your
  own drawing is not also exported as a picture.
