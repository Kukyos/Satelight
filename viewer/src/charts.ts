/**
 * The two charts in the right dock, drawn as plain SVG. Depth runs down, on the same
 * square-root axis the cube uses, so the thermocline gets the room it needs and a depth
 * on the chart is a depth in the cube.
 */

export interface Series {
  name: string;
  color: string;
  values: (number | null | undefined)[];
  dash?: string;
  dots?: boolean;
  width?: number;
}

const NS = "http://www.w3.org/2000/svg";

function el(tag: string, attrs: Record<string, string | number>, text?: string): SVGElement {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = text;
  return e;
}

const depthY = (d: number, top: number, h: number, max = 1000) => top + Math.sqrt(d / max) * h;

function niceTicks(lo: number, hi: number, n = 5): number[] {
  const raw = (hi - lo) / n;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  const step = (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

/** Value (x) against depth (y). Lines break across missing depths; nothing is joined over. */
export function depthChart(svg: SVGSVGElement, depths: number[], series: Series[],
                           opts: { xLabel: string; zeroX?: boolean; height?: number }): void {
  svg.replaceChildren();
  const W = 320;
  const H = opts.height ?? 300;
  const L = 44, R = 12, T = 12, B = 34;
  const w = W - L - R;
  const h = H - T - B;
  const all = series.flatMap((s) => s.values.filter((v): v is number => v != null && Number.isFinite(v)));
  if (!all.length) {
    svg.append(el("text", { x: W / 2, y: H / 2, "text-anchor": "middle" }, "No values to draw"));
    return;
  }
  let lo = Math.min(...all);
  let hi = Math.max(...all);
  if (opts.zeroX) lo = 0;
  const pad = (hi - lo) * 0.06 || 0.5;
  lo -= opts.zeroX ? 0 : pad;
  hi += pad;
  const x = (v: number) => L + ((v - lo) / (hi - lo)) * w;

  for (const d of [0, 50, 100, 200, 300, 500, 700, 1000]) {
    const y = depthY(d, T, h);
    svg.append(el("line", { x1: L, x2: L + w, y1: y, y2: y, stroke: "#1B3350", "stroke-width": 1 }));
    svg.append(el("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, `${d}`));
  }
  for (const v of niceTicks(lo, hi)) {
    svg.append(el("line", { x1: x(v), x2: x(v), y1: T, y2: T + h, stroke: "#13263A", "stroke-width": 1 }));
    svg.append(el("text", { x: x(v), y: T + h + 14, "text-anchor": "middle" }, `${v}`));
  }
  svg.append(el("text", { x: L + w / 2, y: H - 4, "text-anchor": "middle" }, opts.xLabel));
  svg.append(el("text", { x: 10, y: T + h / 2, transform: `rotate(-90 10 ${T + h / 2})`,
                          "text-anchor": "middle" }, "depth (m)"));

  for (const s of series) {
    let path = "";
    let pen = false;
    s.values.forEach((v, k) => {
      if (v == null || !Number.isFinite(v)) { pen = false; return; }
      path += `${pen ? "L" : "M"}${x(v).toFixed(1)},${depthY(depths[k], T, h).toFixed(1)}`;
      pen = true;
    });
    if (path) {
      svg.append(el("path", { d: path, fill: "none", stroke: s.color,
                              "stroke-width": s.width ?? 1.8, "stroke-dasharray": s.dash ?? "",
                              "stroke-linejoin": "round" }));
    }
    if (s.dots) {
      s.values.forEach((v, k) => {
        if (v == null || !Number.isFinite(v)) return;
        svg.append(el("circle", { cx: x(v), cy: depthY(depths[k], T, h), r: 3, fill: s.color }));
      });
    }
  }
}

export function keys(host: HTMLElement, series: Series[]): void {
  host.replaceChildren(...series.map((s) => {
    const span = document.createElement("span");
    span.style.setProperty("--c", s.color);
    span.textContent = s.name;
    return span;
  }));
}
