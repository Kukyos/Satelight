/**
 * Lenses: what the reconstructed water column is *for*. Each one paints the cube's top
 * with a map derived from the day's 15 levels (satelight/api.py /api/lens), keeps the
 * walls as temperature sections so the map's origin stays visible, and shows the
 * harness's score for that quantity against held-out Argo beside climatology and GLORYS.
 *
 *   fishing   depth of the 20 °C isotherm: how deep the warm layer reaches
 *   cyclone   heat potential above 26 °C, with IMD's best track
 *   sonar     mixed-layer depth, where a sonar's surface duct ends
 *   heatwave  a 50–150 m heatwave, and whether the surface hides it
 */

import {
  Cartesian2, Cartesian3, Color, LabelCollection, LabelStyle, Material, NearFarScalar,
  PointPrimitiveCollection, PolylineCollection, VerticalOrigin,
} from "@cesium/engine";
import type { Viewer } from "@cesium/widgets";

import { api, f32, type Eval } from "./api";
import { byId, paletteLut } from "./colorbar";
import { CubeData } from "./cube/data";
import type { Style } from "./cube/paint";

export type LensName = "temperature" | "fishing" | "cyclone" | "sonar" | "heatwave";

interface LensDef {
  label: string;
  palette?: string;
  reversed?: boolean;
  range: [number, number];
  ticks: number[];
  step: number;
  units: string;
  harness?: string;          // key in eval.hazard
  read: string;              // how to read the map, one line
}

export const LENSES: Record<Exclude<LensName, "temperature">, LensDef> = {
  fishing: {
    label: "Fishing depth", palette: "deep", range: [40, 200], ticks: [60, 100, 150], step: 20,
    units: "m to the 20 °C isotherm", harness: "D20 (m)",
    read: "Light: the warm layer is thin and the thermocline shallow, within reach of " +
      "surface gear. Dark: it lies deep. A deep thermocline took tuna schools out of reach " +
      "of purse seiners in the western Indian Ocean (Marsac, IOTC-2008-WPTT-27).",
  },
  cyclone: {
    label: "Cyclone fuel", palette: "matter", range: [0, 160], ticks: [40, 80, 120], step: 20,
    units: "kJ/cm² above 26 °C", harness: "TCHP (kJ/cm²)",
    read: "The heat a cyclone can draw from the sea (Leipper and Volgenau 1972). Watch it " +
      "drain behind the storm as it mixes up cold water.",
  },
  sonar: {
    label: "Sonar layer", palette: "ice", range: [10, 100], ticks: [25, 50, 75], step: 10,
    units: "m, mixed-layer depth", harness: "MLD (m)",
    read: "Mixed-layer depth by temperature (0.2 °C from 10 m; de Boyer Montégut et al. " +
      "2004). A hull sonar's surface duct ends near it. Temperature only, and the 15 " +
      "levels resolve tens of metres, so it is a guide, not a sonic layer depth.",
  },
  heatwave: {
    label: "Hidden heatwaves", range: [0, 2], ticks: [], step: 0,
    units: "",
    read: "Magenta: the 50–150 m layer has been above its 90th percentile for 5 days or " +
      "more while the surface is not, so no satellite image shows it. Orange: the " +
      "surface is in a heatwave too (Hobday et al. 2016, applied to a layer).",
  },
};

const HW_COLORS: [number, number, number][] = [[34, 48, 64], [240, 146, 42], [228, 64, 196]];

function heatwaveLut(): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(256 * 4);
  for (let k = 0; k < 256; k += 1) {
    const c = HW_COLORS[k < 85 ? 0 : k < 171 ? 1 : 2];
    lut.set([c[0], c[1], c[2], 255], k * 4);
  }
  return lut;
}

export function lensStyle(name: Exclude<LensName, "temperature">, base: Style): Style {
  const d = LENSES[name];
  const lut = name === "heatwave" ? heatwaveLut() : paletteLut(byId(d.palette!), d.reversed ?? false);
  return { ...base, lut, lo: d.range[0], hi: d.range[1], knee: undefined, log: false,
           step: d.step, vertical: name === "heatwave" ? "native" : "smooth" };
}

/** The lens map as a one-level cube, so the top face paints it like any section. */
export async function lensTop(name: Exclude<LensName, "temperature">, day: string, region: string,
                              seafloor: Float32Array): Promise<CubeData> {
  const r = await api.lens(day, name, region);
  return new CubeData({ dimensions: [r.dimensions[0], r.dimensions[1], 1], lons: r.lons,
                        lats: r.lats, depths: [0], valueRange: r.range },
                      f32(r.values), seafloor);
}

export function heatwaveLegend(): string {
  return `<span class="sw" style="background:rgb(${HW_COLORS[2]})"></span>hidden below a normal surface ` +
    `<span class="sw" style="background:rgb(${HW_COLORS[1]})"></span>at the surface too`;
}

/** The harness's numbers for this lens in this region, as a small table's rows. */
export function lensScores(ev: Eval | undefined, name: Exclude<LensName, "temperature">,
                           region: string, run: string): string {
  const reg = region === "North Indian Ocean" ? "North Indian Ocean (whole box)" : region;
  if (!ev) return "";
  if (name === "heatwave") {
    const h = ev.heatwave?.["Hidden: warm layer, normal surface"]?.[reg];
    if (!h) return "";
    const row = (k: string, label: string) => {
      const v = h.by[k];
      const f = (x: number | null) => (x == null ? "—" : x.toFixed(2));
      return v ? `<tr><td>${label}</td><td>${f(v.pod)}</td><td>${f(v.far)}</td><td>${f(v.hss)}</td></tr>` : "";
    };
    const head = Object.keys(h.by).find((k) => k.startsWith(`${run} `)) ?? run;
    return `<p class="lede">Against ${h.n.toLocaleString()} held-out Argo casts in the test block, ` +
      `${h.observed} of them in a hidden warm layer that day:</p>` +
      `<table class="scores"><tr><th></th><th>detected</th><th>false alarms</th><th>skill</th></tr>` +
      row(head, "Satelight") + row("GLORYS (ceiling)", "GLORYS") + `</table>` +
      `<p class="note">Detected = share of Argo's hidden layers flagged; skill = Heidke (0 chance, ` +
      `1 perfect). One day per cast. Climatology never flags. From docs/13-eval-results.md.</p>`;
  }
  const q = LENSES[name].harness!;
  const by = ev.hazard?.[q]?.[reg];
  if (!by) return "";
  const head = Object.keys(by).find((k) => k.startsWith(`${run} `)) ?? run;
  const rows: [string, string][] = [["climatology", "Climatology (floor)"], [head, "Satelight"],
                                    ["GLORYS (ceiling)", "GLORYS (ceiling)"]];
  const n = by[head]?.n ?? 0;
  return `<p class="lede">RMSE against ${n.toLocaleString()} held-out Argo casts, ` +
    `${region}, test block (Argo mean ${by[head]?.obs_mean?.toFixed(0) ?? "—"}):</p>` +
    `<table class="scores">` + rows.filter(([k]) => by[k]).map(([k, label]) =>
      `<tr><td>${label}</td><td>${by[k].rmse?.toFixed(1)}</td></tr>`).join("") + `</table>` +
    `<p class="note">${q.replace(/ \(.*\)/, "")} from the same 15 levels for every contender and ` +
    `the float. From docs/13-eval-results.md.</p>`;
}

/** IMD's best track over the cube: the path, dots by grade, and the storm on the day. */
export class Track {
  private lines = new PolylineCollection();
  private dots = new PointPrimitiveCollection();
  private labels = new LabelCollection();
  private points: { time: string; lat: number; lon: number; grade: string; grade_name: string }[] = [];
  source = "";

  constructor(private viewer: Viewer) {
    viewer.scene.primitives.add(this.lines);
    viewer.scene.primitives.add(this.dots);
    viewer.scene.primitives.add(this.labels);
  }

  clear(): void {
    this.lines.removeAll(); this.dots.removeAll(); this.labels.removeAll();
    this.viewer.scene.requestRender();
  }

  async show(name: string, day: string, height: number): Promise<void> {
    this.clear();
    if (!this.points.length || this.source !== name) {
      const r = await api.track(name);
      this.points = r.points;
      this.source = name;
    }
    const pts = this.points;
    const h = height + 6000;
    this.lines.add({
      positions: pts.map((p) => Cartesian3.fromDegrees(p.lon, p.lat, h)), width: 3,
      material: Material.fromType("Color", { color: Color.WHITE.withAlpha(0.85) }),
    });
    const strong = new Set(["SCS", "VSCS", "ESCS", "SUCS"]);
    pts.forEach((p, k) => {
      if (k % 2) return;
      this.dots.add({ position: Cartesian3.fromDegrees(p.lon, p.lat, h), pixelSize: strong.has(p.grade) ? 9 : 6,
                      color: strong.has(p.grade) ? Color.fromCssColorString("#FF4D6D") : Color.WHITE,
                      outlineColor: Color.BLACK, outlineWidth: 1 });
    });
    // The storm on the shown day: IMD's position nearest to that day's noon.
    const noon = Date.parse(`${day}T06:30:00Z`);
    const near = pts.reduce((b, p) => Math.abs(Date.parse(`${p.time.replace(" ", "T")}Z`) - noon) <
      Math.abs(Date.parse(`${b.time.replace(" ", "T")}Z`) - noon) ? p : b, pts[0]);
    const gap = Math.abs(Date.parse(`${near.time.replace(" ", "T")}Z`) - noon);
    if (gap < 12 * 3600e3) {
      this.dots.add({ position: Cartesian3.fromDegrees(near.lon, near.lat, h + 2000), pixelSize: 20,
                      color: Color.fromCssColorString("#FF4D6D"), outlineColor: Color.WHITE, outlineWidth: 3 });
      this.labels.add({
        position: Cartesian3.fromDegrees(near.lon, near.lat, h + 2000),
        text: `${name.toUpperCase()} · ${near.grade_name}`, font: "600 15px Inter, sans-serif",
        fillColor: Color.WHITE, outlineColor: Color.BLACK, outlineWidth: 3, style: LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: VerticalOrigin.BOTTOM, pixelOffset: new Cartesian2(0, -18),
        scaleByDistance: new NearFarScalar(1e6, 1.2, 1e7, 0.7),
      });
    }
    this.viewer.scene.requestRender();
  }
}
