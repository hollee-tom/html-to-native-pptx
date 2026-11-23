"""Native charts, drawn from a `figure[data-chart]` data table in the design's colours.

A chart whose axis minimum is not below its maximum drops both bounds, which PowerPoint would
repair away, and whole-number figures print without a trailing point.
"""

from collections.abc import Sequence
from copy import deepcopy

from lxml import etree
from pptx.chart.chart import Chart
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Pt

from html_to_native_pptx.model import ChartItem
from html_to_native_pptx.writer.colour import paint
from html_to_native_pptx.writer.units import POINTS_PER_PIXEL, emu, place

DEFAULT_COLOURS = ("#4B3BFF", "#FF7A59", "#2BB673", "#F2B705", "#8E44AD", "#16A3B8")


LEGENDS = {
    "top": XL_LEGEND_POSITION.TOP,
    "bottom": XL_LEGEND_POSITION.BOTTOM,
    "right": XL_LEGEND_POSITION.RIGHT,
}


CATEGORY_CHARTS = {
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "bar-stacked": XL_CHART_TYPE.BAR_STACKED,
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "column-stacked": XL_CHART_TYPE.COLUMN_STACKED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "area": XL_CHART_TYPE.AREA,
    "pie": XL_CHART_TYPE.PIE,
    "donut": XL_CHART_TYPE.DOUGHNUT,
    "combo": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "waterfall": XL_CHART_TYPE.COLUMN_STACKED,
    "funnel": XL_CHART_TYPE.BAR_CLUSTERED,
    "gauge": XL_CHART_TYPE.DOUGHNUT,
}


ONE_SERIES = frozenset({"pie", "donut", "waterfall", "funnel", "gauge"})


BY_POINT = frozenset({"pie", "donut"})


def add_chart(shapes: SlideShapes, item: ChartItem) -> None:
    """Add a native chart drawn from the figure's numbers in the design's colours."""
    colours = item.colours or DEFAULT_COLOURS
    if item.chart == "scatter":
        chart = _scatter(shapes, item)
    else:
        data, kind = _category_data(item)
        chart = shapes.add_chart(kind, *place(item.box), data).chart
    _style(chart, item, colours)
    if item.chart == "combo" and len(item.series) > 1:
        _combo(chart)
    if item.chart == "waterfall":
        chart.plots[0].series[0].format.fill.background()
        chart.plots[0].gap_width = 60
    if item.chart == "funnel":
        chart.category_axis.reverse_order = True
        chart.plots[0].gap_width = 20
    if item.chart == "gauge":
        _gauge(chart)


def _category_data(item: ChartItem) -> tuple[CategoryChartData, XL_CHART_TYPE]:
    """The chart's numbers as python-pptx takes them, shaped for the kind of chart."""
    data = CategoryChartData(number_format=_number_format(item.format or "number", _whole(item)))
    series = item.series[:1] if item.chart in ONE_SERIES else item.series
    if item.chart == "waterfall":
        base, change = _waterfall(series[0].values)
        data.categories = list(item.categories)
        data.add_series("", base)
        data.add_series(series[0].name, change)
    elif item.chart == "funnel":
        pairs = sorted(
            zip(item.categories, series[0].values, strict=False),
            key=lambda pair: -(pair[1] or 0),
        )
        data.categories = [name for name, _ in pairs]
        data.add_series(series[0].name, [value for _, value in pairs])
    elif item.chart == "gauge":
        low = item.axis_min if item.axis_min is not None else 0.0
        high = item.axis_max if item.axis_max is not None else 100.0
        value = min(max(series[0].values[0] or low, low), high) if series[0].values else low
        data.categories = ["value", "rest", ""]
        data.add_series(series[0].name, [value - low, high - value, high - low])
    else:
        data.categories = list(item.categories)
        for one in series:
            data.add_series(one.name, list(one.values))
    return data, CATEGORY_CHARTS[item.chart]


def _waterfall(values: Sequence[float | None]) -> tuple[list[float], list[float]]:
    """The invisible base and the visible step of each bar of a waterfall of changes."""
    total = 0.0
    base: list[float] = []
    change: list[float] = []
    for value in values:
        step = value or 0.0
        after = total + step
        base.append(min(total, after))
        change.append(abs(step))
        total = after
    return base, change


def _scatter(shapes: SlideShapes, item: ChartItem) -> Chart:
    """An XY chart: the first series gives each point's x, the others its y."""
    data = XyChartData()
    xs = item.series[0].values
    for one in item.series[1:] or item.series:
        written = data.add_series(one.name)
        for x, y in zip(xs, one.values, strict=False):
            if x is not None and y is not None:
                written.add_data_point(x, y)
    return shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, *place(item.box), data).chart


def _style(chart: Chart, item: ChartItem, colours: Sequence[str]) -> None:
    """Colour the series, set the legend, labels, axis range and text as the figure asks."""
    chart.has_title = False
    if item.legend == "none" or item.chart in {"gauge", "waterfall"}:
        chart.has_legend = False
    else:
        chart.has_legend = True
        chart.legend.position = LEGENDS[item.legend]
        chart.legend.include_in_layout = False
    if item.text_colour is not None or item.size is not None or item.font is not None:
        font = chart.font
        if item.size is not None:
            font.size = Pt(item.size * POINTS_PER_PIXEL)
        if item.font is not None:
            font.name = item.font
        if item.text_colour is not None:
            paint(font.color, item.text_colour)
    plot = chart.plots[0]
    if item.labels and item.chart not in {"gauge", "scatter"}:
        plot.has_data_labels = True
        if item.format is not None:
            plot.data_labels.number_format = _number_format(item.format, _whole(item))
            plot.data_labels.number_format_is_linked = False
    if item.chart in BY_POINT or item.chart == "gauge":
        plot.vary_by_categories = True
        for at, point in enumerate(plot.series[0].points):
            point.format.fill.solid()
            paint(point.format.fill.fore_color, colours[at % len(colours)])
    else:
        for at, series in enumerate(plot.series):
            colour = colours[at % len(colours)]
            if item.chart == "scatter":
                series.format.line.fill.background()
                series.marker.format.fill.solid()
                paint(series.marker.format.fill.fore_color, colour)
            elif item.chart == "line":
                paint(series.format.line.color, colour)
            else:
                series.format.fill.solid()
                paint(series.format.fill.fore_color, colour)
    if item.chart not in BY_POINT and item.chart != "gauge":
        axis = chart.value_axis
        # A minimum at or above the maximum is a chart PowerPoint cannot draw and repairs away.
        bounded = item.axis_min is None or item.axis_max is None or item.axis_min < item.axis_max
        if item.axis_min is not None and bounded:
            axis.minimum_scale = item.axis_min
        if item.axis_max is not None and bounded:
            axis.maximum_scale = item.axis_max
        axis.has_major_gridlines = True
        if item.format is not None:
            axis.tick_labels.number_format = _number_format(item.format, _whole(item))
            axis.tick_labels.number_format_is_linked = False


def _whole(item: ChartItem) -> bool:
    """Whether every figure is a whole number, so labels show "10" rather than "10.0"."""
    return all(
        value is None or float(value).is_integer()
        for series in item.series
        for value in series.values
    )


def _number_format(spec: str, whole: bool = False) -> str:
    """The Excel number format for a figure's `data-format`. A percent figure's values are
    already percentages (45 is 45%), as the chart renderer reads them, so the sign is added
    as text rather than multiplying by 100.
    """
    number = "#,##0" if whole else "#,##0.0#"
    if spec == "percent":
        return f'{number}"%"'
    if spec.startswith("currency:"):
        symbol = {"GBP": "£", "USD": "$", "EUR": "€", "JPY": "¥"}.get(spec[9:])
        return f'"{symbol}"{number}' if symbol else f'{number} "{spec[9:]}"'
    return number


def _combo(chart: Chart) -> None:
    """Move every series after the first into a line chart drawn over the columns, on the
    same axes.
    """
    plot_area = chart._chartSpace.find(qn("c:chart")).find(qn("c:plotArea"))
    bars = plot_area.find(qn("c:barChart"))
    if bars is None:
        return
    lines = etree.Element(qn("c:lineChart"))
    etree.SubElement(lines, qn("c:grouping")).set("val", "standard")
    etree.SubElement(lines, qn("c:varyColors")).set("val", "0")
    moved = bars.findall(qn("c:ser"))[1:]
    for series in moved:
        bars.remove(series)
        for fill in series.findall(qn("c:spPr")):
            colour = fill.find(f"{qn('a:solidFill')}")
            line = etree.SubElement(fill, qn("a:ln"))
            line.set("w", str(int(emu(3))))
            if colour is not None:
                line.append(deepcopy(colour))
                fill.remove(colour)
        etree.SubElement(series, qn("c:smooth")).set("val", "0")
        lines.append(series)
    etree.SubElement(lines, qn("c:marker")).set("val", "1")
    for axis in bars.findall(qn("c:axId")):
        lines.append(deepcopy(axis))
    bars.addnext(lines)


def _gauge(chart: Chart) -> None:
    """Make a doughnut a half ring from the left: the value, the rest, and a hidden half."""
    doughnut = (
        chart._chartSpace.find(qn("c:chart")).find(qn("c:plotArea")).find(qn("c:doughnutChart"))
    )
    if doughnut is None:
        return
    angle = doughnut.find(qn("c:firstSliceAng"))
    if angle is None:
        angle = etree.SubElement(doughnut, qn("c:firstSliceAng"))
    angle.set("val", "270")
    points = chart.plots[0].series[0].points
    points[1].format.fill.solid()
    points[1].format.fill.fore_color.rgb = RGBColor(0xE6, 0xE6, 0xE6)
    points[2].format.fill.background()
