// The page's own chart drawing. nativedeck never reads this: it reads the data table inside
// each figure[data-chart] and writes a native PowerPoint chart. This script only makes the
// HTML show something for the same numbers, as an author's charting code would.
for (const fig of document.querySelectorAll("figure[data-chart]")) {
  const host = fig.querySelector("[data-chart-drawing]");
  const rows = [...fig.querySelectorAll("table[data-chart-data] tbody tr")].map((r) => [...r.cells].map((c) => c.textContent.trim()));
  const names = [...fig.querySelectorAll("table[data-chart-data] thead th")].slice(1).map((c) => c.textContent.trim());
  const colour = (i) => getComputedStyle(fig).getPropertyValue(`--chart-${i + 1}`) || "#888";
  const W = host.clientWidth, H = host.clientHeight, kind = fig.dataset.chart;
  const max = Math.max(...rows.flatMap((r) => r.slice(1).map(Number)));
  let svg = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`;
  if (kind === "pie" || kind === "donut") {
    const total = rows.reduce((s, r) => s + Number(r[1]), 0);
    let angle = -Math.PI / 2;
    rows.forEach((r, i) => {
      const a = (Number(r[1]) / total) * Math.PI * 2, R = Math.min(W, H) / 2 - 4;
      const [x1, y1, x2, y2] = [Math.cos(angle), Math.sin(angle), Math.cos(angle + a), Math.sin(angle + a)];
      svg += `<path d="M${W / 2} ${H / 2} L${W / 2 + R * x1} ${H / 2 + R * y1} A${R} ${R} 0 ${a > Math.PI ? 1 : 0} 1 ${W / 2 + R * x2} ${H / 2 + R * y2}Z" fill="${colour(i)}"/>`;
      angle += a;
    });
  } else {
    const n = rows.length, s = names.length, gw = W / n;
    rows.forEach((r, i) => r.slice(1).forEach((v, j) => {
      const h = (Number(v) / max) * (H - 30), x = i * gw + gw * 0.15 + (j * gw * 0.7) / s;
      if (kind === "line") svg += `<circle cx="${i * gw + gw / 2}" cy="${H - 20 - h}" r="5" fill="${colour(j)}"/>`;
      else svg += `<rect x="${x}" y="${H - 20 - h}" width="${(gw * 0.7) / s - 2}" height="${h}" fill="${colour(j)}"/>`;
    }));
  }
  host.innerHTML = svg + "</svg>";
}
