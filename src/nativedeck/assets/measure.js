/**
 * Runs inside the page, once, and returns the measurements of every slide as JSON.
 * Called as `page.evaluate(script, slideSelector)`; the selector names one element per slide.
 * The result is `{ slides, pictures, fonts }`; see nativedeck/model.py for what each part means.
 */
(selector) => {
  const MARK = "data-nativedeck";
  const probe = document.createElement("i");
  document.body.appendChild(probe);
  const hex = (value, clear = false) => {
    if (!value) return null;
    probe.style.color = "";
    probe.style.color = value;
    const found = getComputedStyle(probe).color.match(/[\d.]+/g);
    if (!found || found.length < 3) return null;
    const alpha = found.length > 3 ? Number(found[3]) : 1;
    if (alpha === 0) return clear ? "#00000000" : null;
    const channels = found.slice(0, 3).map((n) => Math.round(Number(n)));
    // A see-through colour keeps its alpha as a fourth byte, so it is not written solid.
    if (alpha < 1) channels.push(Math.round(alpha * 255));
    return "#" + channels.map((n) => n.toString(16).padStart(2, "0")).join("");
  };
  const px = (value) => { const n = parseFloat(value); return Number.isFinite(n) ? n : 0; };
  // A colour seen through `opacity`: the element's own and its ancestors' up to `stop`, which
  // the browser applies as a group but PowerPoint only knows as each colour's alpha.
  const fade = (colour, opacity) => {
    if (!colour || opacity >= 0.999) return colour;
    const digits = colour.slice(1);
    const alpha = (digits.length === 8 ? parseInt(digits.slice(6), 16) / 255 : 1) * opacity;
    return "#" + digits.slice(0, 6) + Math.round(alpha * 255).toString(16).padStart(2, "0");
  };
  const opacityOf = (el, stop = null) => {
    let opacity = 1;
    for (let at = el; at && at !== stop && at !== document.documentElement; at = at.parentElement)
      opacity *= Number(getComputedStyle(at).opacity);
    return opacity;
  };
  // How far an element and its ancestors turn and scale it, from their 2D transforms.
  const turn = (el) => {
    let angle = 0;
    let scale = 1;
    for (let at = el; at && at !== document.documentElement; at = at.parentElement) {
      const matrix = getComputedStyle(at).transform;
      if (!matrix || matrix === "none") continue;
      const [a, b] = matrix.slice(matrix.indexOf("(") + 1, -1).split(",").map(Number);
      angle += Math.atan2(b, a) * 180 / Math.PI;
      scale *= Math.hypot(a, b);
    }
    return { angle: ((angle % 360) + 360) % 360, scale };
  };
  const shown = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const decorated = (el) => ["::before", "::after"].some((part) => {
    const c = getComputedStyle(el, part).content;
    return c && c !== "none" && c !== "normal";
  });
  let marks = 0;
  const pictures = [];
  const mark = (el, mode, origin) => {
    const id = String(++marks);
    el.setAttribute(MARK, id);
    pictures.push({ id, mode, box: place(el, origin) });
    return id;
  };
  const place = (el, origin) => {
    const r = el.getBoundingClientRect();
    return { x: r.left - origin.left, y: r.top - origin.top, width: r.width, height: r.height };
  };
  const placed = (el, origin) => {
    const box = place(el, origin);
    const { angle, scale } = turn(el);
    if (Math.min(angle, 360 - angle) < 0.1 || !(el.offsetWidth > 0)) return { box, rotation: 0 };
    const width = el.offsetWidth * scale;
    const height = el.offsetHeight * scale;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    return { box: { x: cx - width / 2, y: cy - height / 2, width, height }, rotation: angle };
  };
  const insets = (s) => ({ left: px(s.paddingLeft), top: px(s.paddingTop), right: px(s.paddingRight), bottom: px(s.paddingBottom) });
  const ALIGN = { start: "left", left: "left", center: "center", right: "right", end: "right", justify: "justify" };
  const within = (el, stop, test) => {
    for (let at = el; at && at !== stop.parentElement; at = at.parentElement) if (test(getComputedStyle(at))) return true;
    return false;
  };
  const family = (value) => (value || "").split(",")[0].replace(/["']/g, "").trim() || null;
  const textRun = (node, block, link) => {
    const parent = node.parentElement;
    const s = getComputedStyle(parent);
    if (s.visibility !== "visible" || Number(s.opacity) === 0) return null;
    let value = node.textContent.replace(/[ \t\n\r\f]+/g, " ");
    if (!value) return null;
    if (s.textTransform === "uppercase") value = value.toUpperCase();
    else if (s.textTransform === "lowercase") value = value.toLowerCase();
    const script = within(parent, block, (t) => t.verticalAlign === "super") ? "super"
      : within(parent, block, (t) => t.verticalAlign === "sub") ? "sub" : null;
    let highlight = null;
    for (let at = parent; at && at !== block && !highlight; at = at.parentElement)
      highlight = fade(fillOf(getComputedStyle(at)), opacityOf(at, block));
    const fill = s.webkitTextFillColor && s.webkitTextFillColor !== s.color ? s.webkitTextFillColor : s.color;
    return {
      text: value,
      spacing: s.letterSpacing === "normal" ? 0 : px(s.letterSpacing),
      highlight,
      bold: Number(s.fontWeight) >= 600,
      italic: s.fontStyle !== "normal",
      underline: within(parent, block, (t) => t.textDecorationLine.includes("underline")),
      strike: within(parent, block, (t) => t.textDecorationLine.includes("line-through")),
      script, colour: fade(hex(fill, true), opacityOf(parent, block)),
      size: (px(s.fontSize) * turn(parent).scale) || null, font: family(s.fontFamily),
      weight: Number(s.fontWeight) || null, link,
    };
  };
  const runsOf = (node, block, out, link) => {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) {
        const run = textRun(child, block, link);
        if (run) out.push(run);
      } else if (child.nodeType === 1) {
        const tag = child.tagName;
        if (tag === "BR") out.push({ text: "\n" });
        else if (tag === "UL" || tag === "OL" || tag === "TABLE" || tag === "svg") continue;
        else {
          const style = getComputedStyle(child);
          if (style.display !== "none" && Number(style.opacity) !== 0) {
            const before = px(style.marginLeft) + px(style.borderLeftWidth) + px(style.paddingLeft);
            const after = px(style.paddingRight) + px(style.borderRightWidth) + px(style.marginRight);
            if (before > 1) out.push(gap(style, before));
            runsOf(child, block, out, tag === "A" ? child.href : link);
            if (after > 1) out.push(gap(style, after));
          }
        }
      }
    }
    return out;
  };
  const measurer = document.createElement("canvas").getContext("2d");
  const gap = (style, width) => {
    measurer.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const space = measurer.measureText("\u00a0").width;
    return { text: "\u00a0", spacing: width - space, size: px(style.fontSize) || null, font: family(style.fontFamily), weight: Number(style.fontWeight) || null };
  };
  const tidy = (runs) => {
    // Spaces collapse across runs as the browser collapses them across elements.
    runs.forEach((run, at) => {
      const previous = runs[at - 1];
      if (previous && previous.text.endsWith(" ") && run.text.startsWith(" ")) run.text = run.text.slice(1);
      if (previous && previous.text === "\n") run.text = run.text.replace(/^ +/, "");
      if (runs[at + 1] && runs[at + 1].text === "\n") run.text = run.text.replace(/ +$/, "");
    });
    const kept = runs.filter((run) => run.text !== "");
    if (kept.length && kept[0].text !== "\n") kept[0].text = kept[0].text.replace(/^ +/, "");
    const last = kept[kept.length - 1];
    if (last && last.text !== "\n") last.text = last.text.replace(/ +$/, "");
    return kept.filter((run) => run.text !== "");
  };
  const paragraph = (el, extra) => {
    const s = getComputedStyle(el);
    return Object.assign({
      runs: tidy(runsOf(el, el, [], el.closest("a")?.href || null)),
      align: ALIGN[s.textAlign] || "left",
      line_height: s.lineHeight === "normal" ? null : px(s.lineHeight) || null,
      space_before: 0,
    }, extra || {});
  };
  const listed = (list, level, out) => {
    const ordered = list.tagName === "OL";
    let first = out.length === 0;
    for (const item of list.children) {
      if (item.tagName !== "LI" || !shown(item)) continue;
      const style = getComputedStyle(item).listStyleType;
      out.push(paragraph(item, {
        level,
        bullet: style === "none" ? null : ordered || style === "decimal" ? "number" : "disc",
        space_before: first ? 0 : px(getComputedStyle(item).marginTop),
      }));
      first = false;
      for (const inner of item.children) if (inner.tagName === "UL" || inner.tagName === "OL") listed(inner, level + 1, out);
    }
    return out;
  };
  const fillOf = (s) => (s.backgroundImage === "none" ? hex(s.backgroundColor) : null);
  const text = (el, origin, paragraphs) => {
    const s = getComputedStyle(el);
    const line = s.lineHeight === "normal" ? px(s.fontSize) * 1.2 : px(s.lineHeight);
    const inner = el.getBoundingClientRect().height - px(s.paddingTop) - px(s.paddingBottom);
    const drawn = outline(el, s, origin);
    const { box, rotation } = placed(el, origin);
    return {
      kind: "text", box, rotation, opacity: opacityOf(el), paragraphs, insets: insets(s), fill: fillOf(s),
      radius: px(s.borderTopLeftRadius), line: drawn.line, line_width: drawn.line_width, edges: drawn.edges,
      wrap: paragraphs.length > 1 || !(line > 0) || inner > line * 1.5,
    };
  };
  const border = (s, side) => {
    const width = px(s["border" + side + "Width"]);
    const colour = hex(s["border" + side + "Color"]);
    return width > 0 && colour && s["border" + side + "Style"] !== "none" ? { width, colour } : null;
  };
  // A border on every side alike is an outline. A border on only some sides, such as a rule
  // above a card, is drawn as a strip on each of those sides, never as a box around it.
  const outline = (el, s, origin) => {
    const sides = ["Top", "Right", "Bottom", "Left"].map((side) => border(s, side));
    const [top] = sides;
    if (top && sides.every((b) => b && b.width === top.width && b.colour === top.colour))
      return { line: top.colour, line_width: top.width, edges: [] };
    const { box, rotation } = placed(el, origin);
    const radians = rotation * Math.PI / 180;
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const edges = [];
    sides.forEach((b, at) => {
      if (!b) return;
      const strip = [
        { x: box.x, y: box.y, width: box.width, height: b.width },
        { x: box.x + box.width - b.width, y: box.y, width: b.width, height: box.height },
        { x: box.x, y: box.y + box.height - b.width, width: box.width, height: b.width },
        { x: box.x, y: box.y, width: b.width, height: box.height },
      ][at];
      const dx = strip.x + strip.width / 2 - cx;
      const dy = strip.y + strip.height / 2 - cy;
      const sx = cx + dx * Math.cos(radians) - dy * Math.sin(radians);
      const sy = cy + dx * Math.sin(radians) + dy * Math.cos(radians);
      edges.push({ kind: "shape", box: { ...strip, x: sx - strip.width / 2, y: sy - strip.height / 2 }, rotation,
        opacity: opacityOf(el), shape: "rect", fill: b.colour, line: null, line_width: 0, radius: 0 });
    });
    return { line: null, line_width: 0, edges };
  };
  const MOST_COLUMNS = 75;
  const BLOCKS = new Set(["P", "H1", "H2", "H3", "H4", "H5", "H6", "BLOCKQUOTE", "UL", "OL", "FIGCAPTION", "CITE", "DIV"]);
  const cellFill = (cell, table) => {
    for (let at = cell; at && at !== table.parentElement; at = at.parentElement) {
      const fill = fillOf(getComputedStyle(at));
      if (fill) return fill;
    }
    return null;
  };
  const cellParagraphs = (cell) => {
    const blocks = [...cell.children].filter((child) => BLOCKS.has(child.tagName));
    if (!blocks.length) return [paragraph(cell)];
    return blocks.flatMap((block) => block.tagName === "UL" || block.tagName === "OL" ? listed(block, 0, []) : [paragraph(block)]);
  };
  const table = (el, origin, items) => {
    const caption = el.querySelector(":scope > caption");
    if (caption && shown(caption)) items.push(text(caption, origin, [paragraph(caption)]));
    const rows = [...el.rows].filter(shown);
    if (!rows.length) return;
    const grid = [];
    const cells = [];
    // A span never reaches past the widest row's own cells, or PowerPoint's column limit: a
    // colspan of 1000 is a thousand empty columns the browser draws at no width.
    const widest = Math.min(MOST_COLUMNS, Math.max(1, ...rows.map((row) => row.cells.length)));
    rows.forEach((row, r) => {
      grid[r] = grid[r] || [];
      let c = 0;
      for (const cell of row.cells) {
        while (grid[r][c]) c += 1;
        if (c >= MOST_COLUMNS) break;
        const rowspan = Math.max(1, Math.min(cell.rowSpan || 1, rows.length - r));
        const colspan = Math.max(1, Math.min(cell.colSpan || 1, widest - c, MOST_COLUMNS - c));
        for (let i = 0; i < rowspan; i += 1) {
          grid[r + i] = grid[r + i] || [];
          for (let j = 0; j < colspan; j += 1) grid[r + i][c + j] = true;
        }
        const s = getComputedStyle(cell);
        const valign = s.verticalAlign;
        cells.push({
          el: cell,
          data: {
            row: r, column: c, rowspan, colspan,
            paragraphs: cellParagraphs(cell),
            fill: cellFill(cell, el),
            insets: insets(s),
            vertical: valign === "top" ? "top" : valign === "bottom" ? "bottom" : "middle",
            left: border(s, "Left"), right: border(s, "Right"), top: border(s, "Top"), bottom: border(s, "Bottom"),
          },
        });
        c += colspan;
      }
    });
    const count = Math.max(...grid.map((row) => row.length));
    const first = rows[0].getBoundingClientRect();
    const last = rows[rows.length - 1].getBoundingClientRect();
    const whole = el.getBoundingClientRect();
    const columns = [];
    for (let c = 0; c < count; c += 1) {
      const single = cells.find((cell) => cell.data.column === c && cell.data.colspan === 1);
      columns.push(single ? single.el.getBoundingClientRect().width : whole.width / count);
    }
    items.push({
      kind: "table",
      opacity: opacityOf(el),
      box: { x: whole.left - origin.left, y: first.top - origin.top, width: whole.width, height: last.bottom - first.top },
      columns,
      rows: rows.map((row) => row.getBoundingClientRect().height),
      cells: cells.map((cell) => cell.data),
    });
  };
  const SERIES = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5", "--chart-6"];
  const chart = (el, origin, items, section) => {
    const caption = el.querySelector(":scope > figcaption");
    if (caption && shown(caption)) items.push(text(caption, origin, [paragraph(caption)]));
    const data = el.querySelector(":scope > table[data-chart-data]");
    if (!data) return;
    const head = data.tHead && data.tHead.rows[0] ? [...data.tHead.rows[0].cells] : [];
    const body = data.tBodies[0] ? [...data.tBodies[0].rows] : [];
    const clean = (cell) => (cell.textContent || "").replace(/\s+/g, " ").trim();
    const number = (cell) => { const value = clean(cell); return value === "" ? null : Number(value); };
    const series = head.slice(1).map((cell, at) => ({ name: clean(cell), values: body.map((row) => row.cells[at + 1] ? number(row.cells[at + 1]) : null) }));
    // The page draws no chart without rows, so neither does the export.
    if (!series.length || !body.length) return;
    const drawing = el.querySelector(":scope > [data-chart-drawing]");
    let box = place(drawing && shown(drawing) ? drawing : el, origin);
    if (!(drawing && shown(drawing)) && caption && shown(caption)) {
      const below = caption.getBoundingClientRect().bottom - origin.top;
      box = { x: box.x, y: below, width: box.width, height: Math.max(1, box.y + box.height - below) };
    }
    const tokens = getComputedStyle(el);
    const fromSection = getComputedStyle(section);
    const colours = SERIES.map((name) => hex(tokens.getPropertyValue(name).trim() || fromSection.getPropertyValue(name).trim())).filter(Boolean);
    const s = getComputedStyle(el);
    const attr = (name) => el.getAttribute(name);
    const bound = (name) => { const value = attr(name); return value === null || value === "" ? null : Number(value); };
    let [low, high] = [bound("data-axis-min"), bound("data-axis-max")];
    if (low !== null && high !== null && !(low < high)) [low, high] = [null, null];
    items.push({
      kind: "chart",
      opacity: opacityOf(el),
      box,
      chart: attr("data-chart"),
      categories: body.map((row) => row.cells[0] ? clean(row.cells[0]) : ""),
      series,
      legend: attr("data-legend") || "bottom",
      labels: attr("data-labels") === "on",
      axis_min: low,
      axis_max: high,
      format: attr("data-format"),
      colours,
      text_colour: hex(s.color),
      font: family(s.fontFamily),
      size: px(s.fontSize) || null,
      caption: caption ? clean(caption) : null,
    });
  };
  const TEXT = new Set(["P", "H1", "H2", "H3", "H4", "H5", "H6", "FIGCAPTION"]);
  // Free HTML can put a paragraph in any element. Keep inline marks together, but
  // retain separate measured boxes for layout children, media and native tables/charts.
  const inlineContent = (el) => {
    if (/flex|grid/.test(getComputedStyle(el).display)) return false;
    return [...el.children].every((child) => {
      if (child.tagName === "BR") return true;
      const s = getComputedStyle(child);
      if (s.display === "none" || Number(s.opacity) === 0) return true;
      return s.display === "inline" && !["absolute", "fixed"].includes(s.position)
        && !["IMG", "SVG", "TABLE", "FIGURE"].includes(child.tagName.toUpperCase())
        && s.backgroundImage === "none" && !decorated(child)
        && !["Top", "Right", "Bottom", "Left"].some((side) => border(s, side))
        && inlineContent(child);
    });
  };
  const contents = (el, origin, items, section) => {
    for (const child of el.childNodes) {
      if (child.nodeType === 1) walk(child, origin, items, section);
      else if (child.nodeType === 3 && child.textContent.trim()) {
        // Mixed block/inline content has no element box for its own text. A Range
        // measures just that text, without copying text already handled by children.
        const range = document.createRange();
        range.selectNodeContents(child);
        const box = place(range, origin);
        if (!box.width || !box.height) continue;
        const run = textRun(child, el, el.closest("a")?.href || null);
        if (!run) continue;
        const measured = text(el, origin, [paragraph(el, { runs: tidy([run]), align: "left" })]);
        items.push({ ...measured, box, rotation: 0, insets: { left: 0, top: 0, right: 0, bottom: 0 },
          fill: null, radius: 0, line: null, line_width: 0, edges: [], wrap: range.getClientRects().length > 1 });
      }
    }
  };
  const walk = (el, origin, items, section) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || Number(s.opacity) === 0) return;
    // An element with no box of its own, such as a wrapper whose children are all positioned,
    // or one hidden while a child is shown, paints nothing itself but its children still show.
    if (!shown(el)) {
      if (s.overflow === "visible" || s.visibility === "hidden") contents(el, origin, items, section);
      return;
    }
    const tag = el.tagName;
    if (tag === "FIGURE" && el.hasAttribute("data-chart")) return chart(el, origin, items, section);
    if (tag === "TABLE") return table(el, origin, items);
    if (tag === "IMG" || tag.toLowerCase() === "svg") {
      mark(el, "whole", origin);
      items.push({ kind: "picture", id: el.getAttribute(MARK) });
      return;
    }
    if (el.hasAttribute("data-shape")) {
      if (s.backgroundImage !== "none" || decorated(el)) {
        mark(el, "whole", origin);
        items.push({ kind: "picture", id: el.getAttribute(MARK) });
        return;
      }
      const shape = el.getAttribute("data-shape");
      items.push({
        kind: "shape", ...placed(el, origin), opacity: opacityOf(el), shape: shape === "ellipse" || shape === "line" ? shape : "rect",
        fill: hex(s.backgroundColor), line: border(s, "Top") ? border(s, "Top").colour : null,
        line_width: border(s, "Top") ? border(s, "Top").width : 0, radius: px(s.borderTopLeftRadius),
      });
      return;
    }
    const pictured = s.backgroundImage !== "none" || decorated(el);
    const block = (paragraphs) => {
      if (pictured) {
        mark(el, "background", origin);
        items.push({ kind: "picture", id: el.getAttribute(MARK) });
      }
      const item = text(el, origin, paragraphs);
      items.push(pictured ? { ...item, fill: null } : item);
    };
    if (TEXT.has(tag)) return void block([paragraph(el)]);
    if (tag === "UL" || tag === "OL") return void block(listed(el, 0, []));
    if (tag === "BLOCKQUOTE") {
      const parts = [...el.children].filter((child) => (child.tagName === "P" || child.tagName === "CITE") && shown(child));
      // Text written straight into the quote, ahead of or around a <cite>, is a paragraph too.
      const lead = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).map((n) => textRun(n, el, null)).filter(Boolean);
      const lines = parts.map((part, at) => paragraph(part, { space_before: at || lead.length ? px(getComputedStyle(part).marginTop) : 0 }));
      return void block(lead.length ? [paragraph(el, { runs: tidy(lead) }), ...lines] : lines.length ? lines : [paragraph(el)]);
    }
    if (inlineContent(el) && el.textContent.trim()) return void block([paragraph(el)]);
    const filled = s.backgroundImage === "none" ? hex(s.backgroundColor) : null;
    if (s.backgroundImage !== "none" || decorated(el)) {
      mark(el, "background", origin);
      items.push({ kind: "picture", id: el.getAttribute(MARK) });
    } else {
      const drawn = outline(el, s, origin);
      if (filled || drawn.line) items.push({ kind: "shape", ...placed(el, origin), opacity: opacityOf(el), shape: "rect", fill: filled, line: drawn.line, line_width: drawn.line_width, radius: px(s.borderTopLeftRadius) });
      items.push(...drawn.edges);
    }
    contents(el, origin, items, section);
  };
  const fadedRuns = (paragraphs, opacity) => paragraphs.map((p) => ({ ...p, runs: p.runs.map((run) =>
    ({ ...run, colour: fade(run.colour, opacity), highlight: fade(run.highlight, opacity) })) }));
  const fadedSide = (side, opacity) => side && { ...side, colour: fade(side.colour, opacity) };
  const faded = ({ opacity = 1, ...item }) => {
    if (item.kind === "picture" || opacity >= 0.999) return item;
    if (item.kind === "text") return { ...item, fill: fade(item.fill, opacity), line: fade(item.line, opacity), paragraphs: fadedRuns(item.paragraphs, opacity) };
    if (item.kind === "shape") return { ...item, fill: fade(item.fill, opacity), line: fade(item.line, opacity) };
    if (item.kind === "table") return { ...item, cells: item.cells.map((cell) => ({ ...cell, fill: fade(cell.fill, opacity), paragraphs: fadedRuns(cell.paragraphs, opacity),
      left: fadedSide(cell.left, opacity), right: fadedSide(cell.right, opacity), top: fadedSide(cell.top, opacity), bottom: fadedSide(cell.bottom, opacity) })) };
    if (item.kind === "chart") return { ...item, colours: item.colours.map((c) => fade(c, opacity)), text_colour: fade(item.text_colour, opacity) };
    return item;
  };
  // A match nested inside another match is content of that slide, not a slide of its own.
  const found = [...document.querySelectorAll(selector)];
  const sections = found.filter((el) => !found.some((other) => other !== el && other.contains(el)));
  const slides = sections.map((section) => {
    const origin = section.getBoundingClientRect();
    const s = getComputedStyle(section);
    const items = [];
    let background = null;
    let picture = null;
    if (s.backgroundImage !== "none" || decorated(section)) picture = mark(section, "background", origin);
    else background = hex(s.backgroundColor);
    contents(section, origin, items, section);
    // A side's strip goes over its box, so the box's own fill never hides it.
    const drawn = items.flatMap(({ edges, ...item }) => [item, ...(edges || [])]).map(faded);
    return { background, picture, items: drawn, size: { width: origin.width, height: origin.height } };
  });
  // The fonts the stylesheets declare, each with the absolute addresses of its sources, so the
  // export can carry the files a run was drawn with.
  const WEIGHTS = { normal: 400, bold: 700 };
  const weightOf = (word) => WEIGHTS[word] || Number(word) || 400;
  const fonts = [];
  for (const sheet of document.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch { continue; }
    for (const rule of rules) {
      if (!(rule instanceof CSSFontFaceRule)) continue;
      const sources = [...rule.style.getPropertyValue("src").matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map((m) => m[1]);
      const named = family(rule.style.getPropertyValue("font-family"));
      if (!sources.length || !named) continue;
      const declared = (rule.style.getPropertyValue("font-weight") || "normal").trim().split(/\s+/);
      fonts.push({
        family: named,
        weight: weightOf(declared[0]),
        weight_max: weightOf(declared[declared.length - 1]),
        italic: /italic|oblique/.test(rule.style.getPropertyValue("font-style")),
        sources: sources.map((url) => (url.startsWith("data:") ? url : new URL(url, sheet.href || document.baseURI).href)),
      });
    }
  }
  probe.remove();
  return JSON.stringify({ slides, pictures, fonts });
}
