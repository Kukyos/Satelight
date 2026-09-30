/**
 * The Satelight PoC: the eight satellite fields for a day, the embedding they are
 * compressed into, and the 3D temperature decoded from it, standing on the globe over the
 * Bay of Bengal or the Arabian Sea with the held-out Argo floats of that week inside it.
 *
 * Everything shown comes from satelight/api.py, which only reads what the pipeline and
 * the eval harness wrote. The URL hash carries the view, so a link opens the same scene.
 */

import "@cesium/widgets/Source/widgets.css";
import {
  BoundingSphere,
  Cartesian3,
  Color,
  HeadingPitchRange,
  JulianDate,
  Material,
  Matrix4,
  PointPrimitiveCollection,
  PolylineCollection,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
} from "@cesium/engine";
import { Viewer } from "@cesium/widgets";

import { ApiError, api, f32, u8, type Cast, type Eval, type Meta } from "./api";
import { depthChart, keys, type Series } from "./charts";
import { byId, paletteLut, renderLegend } from "./colorbar";
import { CubeData, type DepthAxis } from "./cube/data";
import { position, rgbFor, type Style } from "./cube/paint";
import { CubeScene } from "./cube/scene";
import { Planet } from "./globe";
import { LANGS, type Lang, type PfzPoint, SECTOR_LANG, Zones, sentence, speak } from "./advisory";
import { LENSES, type LensName, Track, heatwaveLegend, lensScores, lensStyle, lensTop } from "./lens";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const FIELD_LABEL: Record<string, string> = {
  satelight: "Reconstruction", glorys: "GLORYS", error: "Error", climatology: "Climatology",
};
const FIELD_WHAT: Record<string, string> = {
  satelight: "Temperature reconstructed from satellite surface fields alone",
  glorys: "GLORYS12 reanalysis, the training target, for comparison",
  error: "Reconstruction minus GLORYS",
  climatology: "Day-of-year climatology of the training years: the floor",
};
const COLORS: Record<string, string> = {
  satelight: "#E4ECF2", unet: "#E4ECF2", hybrid: "#8FD3C8",
  "unet-no-currents-winds": "#A99BE0", linear: "#8CA0B3", climatology: "#5F7488",
  "GLORYS (ceiling)": "#E8876A", glorys: "#E8876A", argo: "#F5C542",
};
// Tables name runs "unet (selected)", "unet-extended (comparison)": colour by the run.
const color = (name: string) => COLORS[name.replace(/ \(.*\)$/, "")] ?? COLORS[name] ?? "#B8C7D6";
const TEMP_RANGE: [number, number] = [2, 31];
// 26 °C at the middle of the bar, the temperature above which the ocean can feed a
// cyclone: the upper half is that warm layer, where every tropical sea surface lives, the
// lower half the cold water below. Linear, the surface was one colour.
const TEMP_KNEE: [number, number] = [26, 0.5];
const TEMP_PALETTE = "turbo";
const ERROR_RANGE: [number, number] = [-2, 2];
const ARGO = Color.fromCssColorString("#F5C542");

interface State { day: string; region: string; field: string; axis: DepthAxis; lens: LensName }

let meta: Meta;
let evaluation: Eval | undefined;
let state: State;
let cube: CubeScene;
let viewer: Viewer;
let planet: Planet;
let track: Track;
let zones: Zones;
let pfzPoints: PfzPoint[] = [];
const castLines = new PolylineCollection();
const castTops = new PointPrimitiveCollection();
let casts: Cast[] = [];
let lastStyle: Style | undefined;
let lastCube: { data: CubeData; cut: { lon0: number; lon1: number; lat0: number; lat1: number };
                height: number } | undefined;
let selected: { kind: "cast"; cast: Cast } | { kind: "cell"; lat: number; lon: number } | undefined;

// ------------------------------------------------------------------ state in the URL

function readHash(): Partial<State> {
  const p = new URLSearchParams(location.hash.slice(1));
  return Object.fromEntries([...p.entries()]) as Partial<State>;
}

function writeHash(): void {
  history.replaceState(null, "", `#${new URLSearchParams(state as unknown as Record<string, string>)}`);
}

function notice(text: string | null): void {
  const n = $("notice");
  n.textContent = text ?? "";
  n.classList.toggle("on", !!text);
}

// ------------------------------------------------------------------ controls

function segmented(host: HTMLElement, options: [string, string][], current: string,
                   onPick: (v: string) => void): void {
  host.replaceChildren(...options.map(([value, label]) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.setAttribute("aria-pressed", String(value === current));
    b.onclick = () => {
      host.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", "false"));
      b.setAttribute("aria-pressed", "true");
      onPick(value);
    };
    return b;
  }));
}

function style(): Style {
  const error = state.field === "error";
  const [lo, hi] = error ? ERROR_RANGE : TEMP_RANGE;
  return {
    lut: paletteLut(byId(error ? "balance" : TEMP_PALETTE)),
    lo, hi, log: false, knee: error ? undefined : TEMP_KNEE,
    step: error ? 0.5 : 2, vertical: "smooth", axis: state.axis,
    cubeTop: 0, cubeBottom: 1000,
  };
}

function legend(s: Style): void {
  const bar = $<HTMLCanvasElement>("bar");
  const lens = state.lens !== "temperature" ? LENSES[state.lens] : undefined;
  $("bar").hidden = state.lens === "heatwave";
  $("hw-keys").hidden = state.lens !== "heatwave";
  $("hw-keys").innerHTML = state.lens === "heatwave" ? heatwaveLegend() : "";
  bar.getContext("2d")!.drawImage(renderLegend(byId(lens?.palette ?? (state.field === "error" ? "balance" : TEMP_PALETTE)),
                                               lens?.reversed ?? false, 240, 10), 0, 0);
  $("lo").textContent = `${s.lo}`;
  $("hi").textContent = `${s.hi}`;
  // Ticks where they fall on a stretched bar, so its spacing is never read as linear.
  const ticks = lens ? lens.ticks : s.knee ? [10, 20, 26, 29] : [];
  $("ticks").replaceChildren(...ticks.map((v) => Object.assign(document.createElement("span"),
    { textContent: String(v), style: `left:${(position(v, s) * 100).toFixed(1)}%` })));
  $("units").textContent = lens ? (lens.units ? `top: ${lens.units}` : "")
    : state.field === "error" ? "°C, reconstruction − GLORYS" : "°C";
  $("lo").hidden = $("hi").hidden = state.lens === "heatwave";
}

// ------------------------------------------------------------------ the cube

/** The planet around the cube: the same day's satellite SST on the cube's colour bar. */
async function paintOcean(s: Style): Promise<void> {
  const show = state.field !== "error";
  await planet.ocean(state.day, show, s.lut, (v) => position(v, s), `${s.lo}|${s.hi}|${s.knee}`);
  $("around").textContent = show && planet.source
    ? `Around the cube: satellite sea surface temperature, ${planet.source}`
    : "Around the cube: land and sea floor only (the error has no °C colour bar)";
}

async function drawCube(fly = false): Promise<void> {
  try {
    const r = await api.cube(state.day, state.field, state.region);
    const data = new CubeData(
      { dimensions: r.dimensions, lons: r.lons, lats: r.lats, depths: r.depths,
        valueRange: r.valueRange },
      f32(r.values), f32(r.seafloor));
    const s = style();
    const widthM = (r.lons[r.lons.length - 1] - r.lons[0]) * 111_320;
    let top: { data: CubeData; style: Style } | undefined;
    if (state.lens !== "temperature") {
      top = { data: await lensTop(state.lens, state.day, state.region, f32(r.seafloor)),
              style: lensStyle(state.lens, s) };
    }
    cube.render(data, { lon0: r.lons[0], lon1: r.lons[r.lons.length - 1], lat0: r.lats[0],
                        lat1: r.lats[r.lats.length - 1], top: 0, bottom: 1000 },
                s, widthM * 0.36, top);
    lastStyle = s;   // only now: the floats are drawn against the rendered cube's heights
    lastCube = { data, cut: { lon0: r.lons[0], lon1: r.lons[r.lons.length - 1], lat0: r.lats[0],
                              lat1: r.lats[r.lats.length - 1] }, height: widthM * 0.36 };
    legend(top?.style ?? s);
    await Promise.all([drawTrack(), drawZones()]);
    void paintOcean(s);
    drawCasts();
    notice(null);
    if (fly) aim();
  } catch (e) {
    const tier = meta.nowcast?.[state.day];
    notice(tier && state.field !== "satelight"
      ? `${state.day} is a nowcast day: GLORYS does not reach it yet, so there is no ` +
        `${FIELD_LABEL[state.field]} to show. That gap is what the nowcast fills.`
      : e instanceof ApiError ? `Nothing to draw for ${state.day}: ${e.message}` : String(e));
  }
  viewer.scene.requestRender();
}

function aim(): void {
  const x = cube.extent();
  const centre = Cartesian3.fromDegrees(x.lon, x.lat, x.mid);
  viewer.camera.flyToBoundingSphere(new BoundingSphere(centre, x.widthM * 0.55), {
    offset: new HeadingPitchRange(0.42, -0.36, x.widthM * 1.9), duration: 1.6,
  });
}

// ------------------------------------------------------------------ lenses

const STORMS: { name: string; region: string; from: string; to: string }[] = [
  { name: "Mocha", region: "Bay of Bengal", from: "2023-05-03", to: "2023-05-20" },
  { name: "Biparjoy", region: "Arabian Sea", from: "2023-06-02", to: "2023-06-21" },
];

async function drawTrack(): Promise<void> {
  const storm = state.lens === "cyclone" && STORMS.find((x) =>
    (state.region === x.region || state.region === "North Indian Ocean") &&
    state.day >= x.from && state.day <= x.to);
  if (!storm) { track.clear(); return; }
  try { await track.show(storm.name, state.day, cube.heightOf(0)); } catch { track.clear(); }
}

function drawLensCard(): void {
  const card = $("lens-card");
  card.hidden = state.lens === "temperature";
  if (state.lens === "temperature") return;
  const d = LENSES[state.lens];
  $("lens-title").textContent = d.label;
  $("lens-what").textContent = {
    fishing: "How deep the warm layer reaches: the depth of the 20 °C isotherm, the core of the thermocline.",
    cyclone: "The fuel in the sea for a cyclone: heat stored above 26 °C.",
    sonar: "Where the well-mixed top layer ends, and with it a hull sonar's surface duct.",
    heatwave: "Marine heatwaves 50–150 m down, and whether the surface gives them away.",
  }[state.lens];
  $("lens-read").textContent = d.read;
  $("lens-scores").innerHTML = lensScores(evaluation, state.lens, state.region, meta.run);
}

async function drawLensHere(lat: number, lon: number): Promise<void> {
  const box = $("lens-here");
  if (state.lens === "temperature") { box.hidden = true; return; }
  try {
    const r = await api.lensAt(state.day, lat, lon);
    const v = r.values;
    const m = (x: number | null | undefined, u: string) => (x == null ? "—" : `<b>${Math.round(x)}</b> ${u}`);
    const hw = v.heatwave == null ? "—" : ["none", "heatwave at the surface too",
                                           "<b>hidden heatwave</b> below a normal surface"][v.heatwave];
    box.innerHTML = `${r.lat.toFixed(2)}°N ${r.lon.toFixed(2)}°E, ${r.day}<br>` +
      `Warm layer ends (20 °C) at ${m(v.fishing, "m")} · mixed layer ${m(v.sonar, "m")}<br>` +
      `Cyclone fuel ${m(v.cyclone, "kJ/cm²")} · 50–150 m: ${hw}`;
    box.hidden = false;
  } catch { box.hidden = true; }
}

// ------------------------------------------------------------------ the dive

/**
 * From orbit to 1,000 m in one move. The first quarter brings the camera down from space
 * to the cube; then the sea is peeled away from the top, a level at a time: the cube's top
 * becomes the horizontal section at the dive depth, the walls keep what lies below, and
 * the camera follows it down. The gauge shows the depth, the box-mean temperature there
 * from the reconstruction, and the light zone (NOAA National Ocean Service: rarely any
 * significant light below 200 m, some detectable to 1,000 m). The darkening is an
 * illustration of that, not a measured light field.
 *
 * `diveAt(t)` sets the whole scene for t in 0..1, so the film captures it frame by frame
 * and the button plays the same thing in real time.
 */
const DIVE_MS = 14000;
const DIVE_SPACE = 0.22;           // share of the dive spent coming down from orbit
let diving = false;

function diveDepth(t: number): number {
  if (t <= DIVE_SPACE) return 0;
  const u = (t - DIVE_SPACE) / (1 - DIVE_SPACE);
  const e = u * u * (3 - 2 * u);
  return 1000 * e * e;              // slow through the warm layer, faster in the deep
}

function boxMean(data: CubeData, depth: number): number {
  let sum = 0, n = 0;
  const lv = data.levelsAt(depth, "smooth");
  for (let j = 0; j < data.ny; j += 1) {
    for (let i = 0; i < data.nx; i += 1) {
      const v = data.sample(i, j, lv);
      if (v === v) { sum += v; n += 1; }
    }
  }
  return n ? sum / n : NaN;
}

function diveAt(t: number): void {
  if (!lastCube || !lastStyle) return;
  // The floats' sticks stand in the water being peeled away: out of the way while diving.
  castLines.show = castTops.show = false;
  $("view").classList.add("diving");
  const x = cube.extent();
  const depth = diveDepth(t);
  const c = lastCube;
  cube.render(c.data, { ...c.cut, top: Math.min(depth, 995), bottom: 1000 }, lastStyle, c.height);
  const ease = (u: number) => u * u * (3 - 2 * u);
  const a = ease(Math.min(1, t / DIVE_SPACE));
  const range = x.widthM * (a < 1 ? 9 - 7.1 * a : 1.9 - 0.35 * ((t - DIVE_SPACE) / (1 - DIVE_SPACE)));
  const pitch = a < 1 ? -1.35 + 0.99 * a : -0.36 - 0.1 * ((t - DIVE_SPACE) / (1 - DIVE_SPACE));
  const heading = 0.1 + 0.5 * t;
  const target = Cartesian3.fromDegrees(x.lon, x.lat, cube.heightOf(depth) - x.widthM * 0.05);
  viewer.camera.viewBoundingSphere(new BoundingSphere(target, x.widthM * 0.55),
                                   new HeadingPitchRange(heading, pitch, range));
  viewer.camera.lookAtTransform(Matrix4.IDENTITY);
  // The gauge and the light.
  const g = $("gauge");
  g.hidden = t <= DIVE_SPACE * 0.8;
  const mean = boxMean(c.data, Math.max(depth, 0));
  $("gauge-depth").textContent = `${Math.round(depth).toLocaleString()} m`;
  $("gauge-temp").textContent = Number.isFinite(mean) ? `${mean.toFixed(1)} °C, ${state.region} mean` : "";
  $("gauge-zone").textContent = depth < 200 ? "Sunlight zone" : depth < 1000 ? "Twilight zone" : "Darkness";
  $("dark").style.opacity = String(0.8 * (1 - Math.exp(-depth / 220)));
  viewer.scene.render();
}

function endDive(): void {
  diving = false;
  $("view").classList.remove("diving");
  castLines.show = castTops.show = true;
  $("gauge").hidden = true;
  $("dark").style.opacity = "0";
  $("dive").textContent = "Dive";
  void drawCube(true);
}

function dive(): void {
  if (diving) { endDive(); return; }
  if (state.lens !== "temperature") $<HTMLButtonElement>("lenses").querySelector("button")!.click();
  diving = true;
  $("dive").textContent = "Stop";
  const t0 = performance.now();
  const step = () => {
    if (!diving) return;
    const t = Math.min(1, (performance.now() - t0) / DIVE_MS);
    diveAt(t);
    if (t < 1) requestAnimationFrame(step);
    else setTimeout(() => diving && endDive(), 2500);
  };
  requestAnimationFrame(step);
}

// ------------------------------------------------------------------ fishing zones

const lastDay = () => meta.days[meta.days.length - 1];

async function drawZones(): Promise<void> {
  const box = $("pfz");
  const on = state.lens === "fishing";
  box.hidden = !on;
  if (!on) { zones.clear(); return; }
  if (state.day !== lastDay()) {
    zones.clear();
    $("pfz-lede").textContent = "INCOIS issues its Potential Fishing Zone advisories for today. " +
      "Press Now to pair them with the latest reconstruction.";
    $("pfz-list").replaceChildren();
    $("pfz-note").textContent = "";
    $("pfz-sector").hidden = $("pfz-lang").hidden = true;
    return;
  }
  $("pfz-sector").hidden = $("pfz-lang").hidden = false;
  try {
    const r = await api.pfz(state.day);
    pfzPoints = r.points;
    const b = meta.regions[state.region];
    zones.show(pfzPoints.filter((x) => x.lon >= b.lon[0] && x.lon <= b.lon[1] &&
                                       x.lat >= b.lat[0] && x.lat <= b.lat[1]), cube.heightOf(0));
    const sel = $<HTMLSelectElement>("pfz-sector");
    if (!sel.options.length) {
      sel.replaceChildren(...r.sectors.map((x) => new Option(
        `${x.name}${x.status === "ok" ? "" : ` (${x.status === "none" ? "cloud, no advisory" : x.status})`}`, x.sector)));
      sel.value = state.region === "Arabian Sea" ? "SEC005" : "SEC007";
      const lang = $<HTMLSelectElement>("pfz-lang");
      lang.replaceChildren(...Object.entries(LANGS).map(([k, v]) => new Option(v.name, k)));
      lang.value = SECTOR_LANG[sel.value];
      sel.onchange = () => { lang.value = SECTOR_LANG[sel.value]; listZones(); };
      lang.onchange = () => listZones();
    }
    $("pfz-lede").textContent = `${r.points.length} zones from INCOIS (fetched ${r.fetched_utc}), ` +
      `each with how deep the warm water goes there on ${state.day}, the latest day the ` +
      `satellites allow. INCOIS says where; Satelight says how deep.`;
    listZones();
  } catch (e) {
    zones.clear();
    $("pfz-lede").textContent = `INCOIS advisories unavailable: ${(e as Error).message}`;
  }
}

function listZones(): void {
  const sec = $<HTMLSelectElement>("pfz-sector").value;
  const lang = $<HTMLSelectElement>("pfz-lang").value as Lang;
  const rows = pfzPoints.filter((x) => x.sector === sec)
    .map((x) => ({ x, text: sentence(x, lang, state.day) }))
    .filter((r) => r.text).slice(0, 6);
  $("pfz-list").replaceChildren(...rows.map(({ text }) => {
    const d = document.createElement("div");
    d.className = "zone";
    const b = document.createElement("button");
    b.textContent = "🔊";
    b.title = "Read aloud";
    b.onclick = () => { $("pfz-note").textContent = speak(text!, lang); };
    const t = document.createElement("div");
    t.textContent = text!;
    d.append(b, t);
    return d;
  }));
  if (!rows.length) $("pfz-list").replaceChildren(Object.assign(document.createElement("p"),
    { className: "empty", textContent: "No zone in this sector today, or none Satelight can add to." }));
  $("pfz-note").textContent = (lang === "en" ? "" : "Machine-translated; not yet checked by a native speaker. ") +
    (sec === "SEC003" ? "Goa's language is Konkani, not here yet. " : "") +
    "Zones: INCOIS, as published. Depths: Satelight, satellites only.";
}

// ------------------------------------------------------------------ Argo floats

function drawCasts(): void {
  castLines.removeAll();
  castTops.removeAll();
  const s = lastStyle;
  if (!s || state.field === "error") return;
  const box = meta.regions[state.region];
  const depths = meta.depths;
  casts.forEach((c, index) => {
    if (c.lon < box.lon[0] || c.lon > box.lon[1] || c.lat < box.lat[0] || c.lat > box.lat[1]) return;
    let prev = -1;
    c.obs.forEach((v, k) => {
      if (v == null) { prev = -1; return; }
      if (prev >= 0) {
        const mid = (c.obs[prev]! + v) / 2;
        const [r, g, b] = rgbFor(mid, s);
        castLines.add({
          positions: [Cartesian3.fromDegrees(c.lon, c.lat, cube.heightOf(depths[prev]) + 600),
                      Cartesian3.fromDegrees(c.lon, c.lat, cube.heightOf(depths[k]) + 600)],
          width: 4,
          material: Material.fromType("Color", { color: Color.fromBytes(r, g, b, 255) }),
        });
      }
      prev = k;
    });
    castTops.add({
      position: Cartesian3.fromDegrees(c.lon, c.lat, cube.heightOf(0) + 8000),
      color: ARGO, pixelSize: 9, outlineColor: Color.fromCssColorString("#0D1B2A"),
      outlineWidth: 2, id: { cast: index },
    });
  });
}

async function loadCasts(): Promise<void> {
  try {
    casts = (await api.casts(state.day)).casts;
  } catch {
    casts = [];
  }
  drawCasts();
}

// ------------------------------------------------------------------ left rail

const INPUT_PALETTE: Record<string, [string, boolean]> = {
  sst: ["thermal", false], sss: ["haline", false], adt: ["viridis", false],
  sla: ["balance", true], uc: ["balance", true], vc: ["balance", true],
  uw: ["balance", true], vw: ["balance", true],
};

async function drawInputs(): Promise<void> {
  const host = $("inputs");
  try {
    const r = await api.inputs(state.day);
    const [ny, nx] = r.shape;
    host.replaceChildren(...r.inputs.map((f) => {
      const wrap = document.createElement("div");
      wrap.className = "input";
      const canvas = document.createElement("canvas");
      canvas.width = nx;
      canvas.height = ny;
      const [pal, symmetric] = INPUT_PALETTE[f.key] ?? ["viridis", false];
      let [lo, hi] = f.range;
      if (symmetric) { const m = Math.max(Math.abs(lo), Math.abs(hi)); lo = -m; hi = m; }
      const lut = paletteLut(byId(pal));
      const v = f32(f.values);
      const img = new ImageData(nx, ny);
      for (let j = 0; j < ny; j += 1) {
        for (let i = 0; i < nx; i += 1) {
          const val = v[j * nx + i];
          const o = ((ny - 1 - j) * nx + i) * 4;
          if (!Number.isFinite(val)) { img.data.set([27, 39, 52, 255], o); continue; }
          const k = Math.max(0, Math.min(255, Math.round(((val - lo) / (hi - lo)) * 255)));
          img.data.set([lut[k * 4], lut[k * 4 + 1], lut[k * 4 + 2], 255], o);
        }
      }
      canvas.getContext("2d")!.putImageData(img, 0, 0);
      canvas.title = f.source ? `${f.title} — ${f.source}` : f.title;
      const name = document.createElement("div");
      name.className = "name";
      name.textContent = f.title;
      const range = document.createElement("div");
      range.className = "range";
      range.textContent = `${lo.toFixed(2)} to ${hi.toFixed(2)} ${f.units}`;
      wrap.append(canvas, name, range);
      return wrap;
    }));
  } catch (e) {
    host.replaceChildren(Object.assign(document.createElement("p"),
      { className: "empty", textContent: `No inputs for ${state.day}: ${(e as Error).message}` }));
  }
}

async function drawEmbedding(): Promise<void> {
  const canvas = $<HTMLCanvasElement>("emb");
  const ctx = canvas.getContext("2d")!;
  try {
    const r = await api.embedding(state.day);
    const [ny, nx] = r.shape;
    const rgb = u8(r.rgb);
    const sea = u8(r.sea);
    const img = new ImageData(nx, ny);
    for (let j = 0; j < ny; j += 1) {
      for (let i = 0; i < nx; i += 1) {
        const s = j * nx + i;
        const o = ((ny - 1 - j) * nx + i) * 4;
        if (!sea[s]) { img.data.set([27, 39, 52, 255], o); continue; }
        img.data.set([rgb[s * 3], rgb[s * 3 + 1], rgb[s * 3 + 2], 255], o);
      }
    }
    ctx.putImageData(img, 0, 0);
    $("emb-lede").textContent = `Each cell's surface state compressed to ${r.dims} numbers by ` +
      `the ${r.run} encoder. The first three principal components are shown as colour: ` +
      `cells of one colour look alike to the model.`;
  } catch {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    $("emb-lede").textContent = meta.nowcast?.[state.day]
      ? "The embedding is saved for the test block only; this nowcast day was decoded, not archived."
      : "No embedding saved for this day.";
  }
}

// ------------------------------------------------------------------ right rail

async function drawProfile(): Promise<void> {
  const svg = document.getElementById("profile") as unknown as SVGSVGElement;
  const depths = meta.depths;
  if (!selected) {
    svg.replaceChildren();
    return;
  }
  let series: Series[] = [];
  if (selected.kind === "cast") {
    const c = selected.cast;
    $("where").textContent = `Argo float ${c.platform}, cycle ${c.cycle ?? "?"}, ${c.day} · ` +
      `${c.lat.toFixed(2)}°N ${c.lon.toFixed(2)}°E`;
    series = [
      ...Object.entries(c.pred).map(([k, v]) => ({
        name: k === "GLORYS (ceiling)" ? "GLORYS" : k, color: color(k), values: v,
        dash: k === "climatology" ? "2 4" : k === "linear" ? "6 4" : undefined,
        width: k.startsWith(`${meta.run} `) || k === meta.run ? 2.4 : 1.4,
      })),
      { name: "Argo, measured", color: color("argo"), values: c.obs, dots: true, width: 1 },
    ];
    $("profile-prov").textContent = `Data mode ${c.data_mode}; ${c.levels_rejected} levels failed QC ` +
      `and were left out. Source: ${c.source_file}. This profile is from the held-out test ` +
      `block: the model never saw it, but GLORYS assimilates Argo (see 03-limitations L1).`;
  } else {
    const col = await api.column(state.day, selected.lat, selected.lon);
    $("where").textContent = `${col.lat.toFixed(3)}°N ${col.lon.toFixed(3)}°E on ${col.day}` +
      (col.seafloor ? ` · sea floor ${Math.round(col.seafloor).toLocaleString()} m` : "");
    series = Object.entries(col.profiles).map(([k, v]) => ({
      name: FIELD_LABEL[k] ?? k, color: color(k === "satelight" ? meta.run : k), values: v,
      dash: k === "climatology" ? "2 4" : undefined, width: k === "satelight" ? 2.4 : 1.4,
    }));
    $("profile-prov").textContent = meta.zero_metre_rule;
  }
  depthChart(svg, depths, series, { xLabel: "temperature (°C)" });
  keys($("profile-keys"), series);
}

function drawSkill(): void {
  const svg = document.getElementById("skill") as unknown as SVGSVGElement;
  if (!evaluation) {
    $("skill-lede").textContent = "The eval harness has not run yet.";
    return;
  }
  const region = state.region === "North Indian Ocean" ? "North Indian Ocean (whole box)" : state.region;
  const table = evaluation.argo[region];
  if (!table) return;
  const series: Series[] = Object.entries(table).map(([name, per]) => ({
    name: name === "GLORYS (ceiling)" ? "GLORYS (ceiling)" : name,
    color: color(name), values: per.map((s) => s.rmse),
    dash: name === "climatology" ? "2 4" : name === "linear" ? "6 4" : undefined,
    width: name.startsWith(`${meta.run} `) || name === meta.run ? 2.4 : 1.4,
  }));
  const n = table[Object.keys(table)[0]].reduce((a, s) => a + (s.n ?? 0), 0);
  $("skill-lede").textContent = `RMSE against held-out Argo floats, ${state.region}, test block ` +
    `(${n.toLocaleString()} float-depth pairs). Lower is better. From docs/13-eval-results.md.`;
  depthChart(svg, meta.depths, series, { xLabel: "RMSE (°C)", zeroX: true, height: 260 });
  keys($("skill-keys"), series);
}

// ------------------------------------------------------------------ time

function setDay(day: string): void {
  state.day = day;
  // 06:30 UTC is about noon at the box's middle longitude (75°E).
  viewer.clock.currentTime = JulianDate.fromIso8601(`${day}T06:30:00Z`);
  const d = new Date(`${day}T00:00:00Z`);
  $("date").textContent = d.toLocaleDateString("en-GB", { day: "numeric", month: "long",
                                                           year: "numeric", timeZone: "UTC" });
  const tier = meta.nowcast?.[day];
  const early = meta.prefloat && day <= meta.prefloat[1];
  $("what").innerHTML = tier ? `<span class="badge">NOWCAST</span>` +
    `near-real-time inputs (${meta.nowcast_tiers[tier].inputs}); no reanalysis covers this day yet · `
    : early ? `<span class="badge">BEFORE THE FLOATS</span>comparison: trained on 2010–2020, ` +
    `and salinity before 2010 is not from a satellite · ` : "";
  $("what").append(state.lens === "temperature"
    ? `${FIELD_WHAT[state.field]} · ${state.region}`
    : `Top: ${LENSES[state.lens].label.toLowerCase()} · sides: ${FIELD_LABEL[state.field].toLowerCase()} · ${state.region}`);
  writeHash();
}

let playing: number | undefined;

async function refreshDay(): Promise<void> {
  setDay(meta.days[+$<HTMLInputElement>("day").value]);
  await Promise.all([drawCube(), drawInputs(), drawEmbedding(), loadCasts()]);
  if (selected?.kind === "cell") await drawProfile();
  if (selected) {
    const at = selected.kind === "cast" ? selected.cast : selected;
    await drawLensHere(at.lat, at.lon);
  }
}

function play(): void {
  const btn = $("play");
  if (playing) {
    clearInterval(playing);
    playing = undefined;
    btn.textContent = "▶";
    btn.setAttribute("aria-label", "Play");
    return;
  }
  btn.textContent = "❚❚";
  btn.setAttribute("aria-label", "Pause");
  let busy = false;
  playing = window.setInterval(async () => {
    if (busy) return;
    busy = true;
    const slider = $<HTMLInputElement>("day");
    slider.value = String((+slider.value + 3) % meta.days.length);
    setDay(meta.days[+slider.value]);
    await Promise.all([drawCube(), drawInputs(), drawEmbedding(), loadCasts()]);
    busy = false;
  }, 450);
}

// ------------------------------------------------------------------ start

async function start(): Promise<void> {
  viewer = new Viewer("globe", {
    animation: false, timeline: false, baseLayerPicker: false, geocoder: false,
    homeButton: false, sceneModePicker: false, navigationHelpButton: false, infoBox: false,
    selectionIndicator: false, fullscreenButton: false, baseLayer: false,
  });
  viewer.scene.globe.baseColor = Color.fromCssColorString("#0b2238");
  viewer.scene.backgroundColor = Color.fromCssColorString("#0D1B2A");
  if (viewer.scene.skyAtmosphere) viewer.scene.skyAtmosphere.show = true;
  viewer.scene.requestRenderMode = true;
  // Sunlight where it really falls: the clock stands at local noon over the box on the
  // shown day (setDay), so the far side of the planet is night and the globe has shape.
  viewer.scene.globe.enableLighting = true;
  viewer.scene.globe.showGroundAtmosphere = true;
  planet = new Planet(viewer);
  await planet.land();
  viewer.scene.primitives.add(castLines);
  viewer.scene.primitives.add(castTops);
  cube = new CubeScene(viewer.scene);
  track = new Track(viewer);
  zones = new Zones(viewer);

  meta = await api.meta();
  if (!meta.days.length) {
    notice("No reconstruction has been written yet. Run python -m satelight.predict first.");
    return;
  }
  try { evaluation = await api.evaluation(); } catch { evaluation = undefined; }

  const h = readHash();
  state = {
    day: meta.days.includes(h.day ?? "") ? h.day!
      : meta.days[Math.min(meta.days.indexOf(meta.splits.test[0]) + 160, meta.days.length - 1)],
    region: meta.regions[h.region ?? ""] ? h.region! : "Bay of Bengal",
    field: meta.fields.includes(h.field ?? "") ? h.field! : "satelight",
    axis: h.axis === "linear" ? "linear" : "stretched",
    lens: (["fishing", "cyclone", "sonar", "heatwave"] as string[]).includes(h.lens ?? "")
      ? h.lens as LensName : "temperature",
  };

  const slider = $<HTMLInputElement>("day");
  slider.max = String(meta.days.length - 1);
  slider.value = String(meta.days.indexOf(state.day));
  slider.oninput = () => setDay(meta.days[+slider.value]);
  slider.onchange = () => void refreshDay();
  const firstNow = Object.keys(meta.nowcast ?? {}).sort()[0];
  $("span").textContent = [
    meta.prefloat ? `${meta.prefloat[0].slice(0, 4)}–${meta.prefloat[1].slice(0, 4)} before the floats` : "",
    `${meta.splits.test[0]} → ${meta.splits.test[1]} test block`,
    firstNow ? `${firstNow} → ${lastDay()} nowcast` : ""].filter(Boolean).join(" · ");
  $("now").hidden = !firstNow;
  $("now").onclick = () => {
    $<HTMLInputElement>("day").value = String(meta.days.length - 1);
    void refreshDay();
  };
  $("play").onclick = play;

  segmented($("regions"), Object.keys(meta.regions).map((r) => [r, r]), state.region, (r) => {
    state.region = r;
    setDay(state.day);
    void drawCube(true);
    drawSkill();
    drawLensCard();
  });
  segmented($("fields"), meta.fields.map((f) => [f, FIELD_LABEL[f] ?? f]), state.field, (f) => {
    state.field = f;
    setDay(state.day);
    void drawCube();
  });
  $("dive").onclick = dive;
  segmented($("lenses"), [["temperature", "Temperature"],
    ...Object.entries(LENSES).map(([k, d]) => [k, d.label] as [string, string])], state.lens, (l) => {
    state.lens = l as LensName;
    setDay(state.day);
    drawLensCard();
    void drawCube();
    if (selected?.kind === "cell") void drawLensHere(selected.lat, selected.lon);
    else if (selected?.kind === "cast") void drawLensHere(selected.cast.lat, selected.cast.lon);
  });
  segmented($("axis"), [["stretched", "√ depth"], ["linear", "Linear depth"]], state.axis, (a) => {
    state.axis = a as DepthAxis;
    writeHash();
    void drawCube();
  });

  const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction(async (click: { position: import("@cesium/engine").Cartesian2 }) => {
    const picked = viewer.scene.pick(click.position);
    if (picked?.id && typeof picked.id === "object" && "cast" in picked.id) {
      selected = { kind: "cast", cast: casts[(picked.id as { cast: number }).cast] };
    } else {
      const p = cube.probe(click.position);
      if (!p) return;
      selected = { kind: "cell", lat: p.lat, lon: p.lon };
    }
    await drawProfile();
    const at = selected.kind === "cast" ? selected.cast : selected;
    await drawLensHere(at.lat, at.lon);
  }, ScreenSpaceEventType.LEFT_CLICK);

  setDay(state.day);
  drawSkill();
  drawLensCard();
  await Promise.all([drawCube(true), drawInputs(), drawEmbedding(), loadCasts()]);
  // A linked day with no reconstruction (an input was missing that day, see
  // data/output/daily/manifest.json) is said so, not silently swapped for another day.
  if (h.day && h.day !== state.day) {
    notice(`No reconstruction was written for ${h.day}: an input had no data that day. ` +
      `Showing ${state.day} instead.`);
  }
  // Open on the first float in view, so the right dock is never empty on a demo.
  const first = casts.find((c) => {
    const b = meta.regions[state.region];
    return c.lon >= b.lon[0] && c.lon <= b.lon[1] && c.lat >= b.lat[0] && c.lat <= b.lat[1];
  });
  // Otherwise the column at the middle of the basin, so the right dock is never empty.
  // The whole box's middle is on land (central India): use the Bay's there.
  const b = meta.regions[state.region === "North Indian Ocean" ? "Bay of Bengal" : state.region];
  selected = first ? { kind: "cast", cast: first }
    : { kind: "cell", lat: (b.lat[0] + b.lat[1]) / 2, lon: (b.lon[0] + b.lon[1]) / 2 };
  await drawProfile();
  // A handle for the deck and film capture scripts (submission/capture.cjs, video/capture.cjs):
  // they drive the camera frame by frame and pick a float without a mouse.
  Object.assign(window, { sl: {
    viewer, cube, meta, state: () => state, casts: () => casts,
    ready: true,
    pickCast: async (i: number) => {
      selected = { kind: "cast", cast: casts[i] };
      await Promise.all([drawProfile(), drawLensHere(casts[i].lat, casts[i].lon)]);
    },
    pickCell: async (lat: number, lon: number) => {
      selected = { kind: "cell", lat, lon };
      await Promise.all([drawProfile(), drawLensHere(lat, lon)]);
    },
    // Camera about the cube, set at once (no flight), and one explicit render.
    orbit: (heading: number, pitch: number, range = 1.9) => {
      const x = cube.extent();
      viewer.camera.viewBoundingSphere(
        new BoundingSphere(Cartesian3.fromDegrees(x.lon, x.lat, x.mid), x.widthM * 0.55),
        new HeadingPitchRange(heading, pitch, x.widthM * range));
      viewer.camera.lookAtTransform(Matrix4.IDENTITY);
      viewer.scene.render();
    },
    // Capture quality: every device pixel rendered (Cesium otherwise renders at CSS
    // pixels on a high-density screen) and 4x MSAA.
    hq: () => {
      viewer.useBrowserRecommendedResolution = false;
      viewer.scene.msaaSamples = 4;
    },
    // Render until every imagery and terrain tile in view has arrived, so a photograph is
    // never taken of a blurry placeholder tile. Tiles load through images, not fetch, so
    // the capture scripts' network count cannot see them.
    sharp: async (maxMs = 20000) => {
      const t0 = performance.now();
      viewer.scene.render();
      while (!viewer.scene.globe.tilesLoaded && performance.now() - t0 < maxMs) {
        await new Promise((r) => setTimeout(r, 50));
        viewer.scene.render();
      }
      viewer.scene.render();
    },
    diveAt: (t: number) => diveAt(t),
    endDive: () => endDive(),
    // After a partial dive in a capture: the cube whole again and the gauge off, no fly-to.
    endDiveQuiet: () => {
      if (!lastCube || !lastStyle || !$("view").classList.contains("diving")) return;
      $("view").classList.remove("diving");
      $("gauge").hidden = true;
      $("dark").style.opacity = "0";
      castLines.show = castTops.show = true;
      cube.render(lastCube.data, { ...lastCube.cut, top: 0, bottom: 1000 }, lastStyle, lastCube.height);
    },
    setLens: (l: string) => {
      [...document.querySelectorAll<HTMLButtonElement>("#lenses button")]
        .find((b) => b.textContent === (l === "temperature" ? "Temperature" : LENSES[l as keyof typeof LENSES].label))
        ?.click();
    },
    setDay: async (day: string) => {
      $<HTMLInputElement>("day").value = String(meta.days.indexOf(day));
      await refreshDay();
    },
  } });
}

void start();
