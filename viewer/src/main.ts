/**
 * The OceanEmbed PoC: the eight satellite fields for a day, the embedding they are
 * compressed into, and the 3D temperature decoded from it, standing on the globe over the
 * Bay of Bengal or the Arabian Sea with the held-out Argo floats of that week inside it.
 *
 * Everything shown comes from oceanembed/api.py, which only reads what the pipeline and
 * the eval harness wrote. The URL hash carries the view, so a link opens the same scene.
 */

import "@cesium/widgets/Source/widgets.css";
import {
  BoundingSphere,
  Cartesian3,
  Color,
  HeadingPitchRange,
  ImageryLayer,
  Material,
  Matrix4,
  PointPrimitiveCollection,
  PolylineCollection,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  TileMapServiceImageryProvider,
} from "@cesium/engine";
import { Viewer } from "@cesium/widgets";

import { ApiError, api, f32, u8, type Cast, type Eval, type Meta } from "./api";
import { depthChart, keys, type Series } from "./charts";
import { byId, paletteLut, renderLegend } from "./colorbar";
import { CubeData, type DepthAxis } from "./cube/data";
import { rgbFor, type Style } from "./cube/paint";
import { CubeScene } from "./cube/scene";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const FIELD_LABEL: Record<string, string> = {
  oceanembed: "Reconstruction", glorys: "GLORYS", error: "Error", climatology: "Climatology",
};
const FIELD_WHAT: Record<string, string> = {
  oceanembed: "Temperature reconstructed from satellite surface fields alone",
  glorys: "GLORYS12 reanalysis, the training target, for comparison",
  error: "Reconstruction minus GLORYS",
  climatology: "Day-of-year climatology of the training years: the floor",
};
const COLORS: Record<string, string> = {
  oceanembed: "#E4ECF2", unet: "#E4ECF2", hybrid: "#8FD3C8",
  "unet-no-currents-winds": "#A99BE0", linear: "#8CA0B3", climatology: "#5F7488",
  "GLORYS (ceiling)": "#E8876A", glorys: "#E8876A", argo: "#F5C542",
};
// Tables name runs "unet (selected)", "unet-extended (comparison)": colour by the run.
const color = (name: string) => COLORS[name.replace(/ \(.*\)$/, "")] ?? COLORS[name] ?? "#B8C7D6";
const TEMP_RANGE: [number, number] = [2, 31];
const ERROR_RANGE: [number, number] = [-2, 2];
const ARGO = Color.fromCssColorString("#F5C542");

interface State { day: string; region: string; field: string; axis: DepthAxis }

let meta: Meta;
let evaluation: Eval | undefined;
let state: State;
let cube: CubeScene;
let viewer: Viewer;
const castLines = new PolylineCollection();
const castTops = new PointPrimitiveCollection();
let casts: Cast[] = [];
let lastStyle: Style | undefined;
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
    lut: paletteLut(byId(error ? "balance" : "thermal")),
    lo, hi, log: false, step: error ? 0.5 : 2, vertical: "smooth", axis: state.axis,
    cubeTop: 0, cubeBottom: 1000,
  };
}

function legend(s: Style): void {
  const bar = $<HTMLCanvasElement>("bar");
  bar.getContext("2d")!.drawImage(renderLegend(byId(state.field === "error" ? "balance" : "thermal"),
                                               false, 240, 10), 0, 0);
  $("lo").textContent = `${s.lo}`;
  $("hi").textContent = `${s.hi}`;
  $("units").textContent = state.field === "error" ? "°C, reconstruction − GLORYS" : "°C";
}

// ------------------------------------------------------------------ the cube

async function drawCube(fly = false): Promise<void> {
  try {
    const r = await api.cube(state.day, state.field, state.region);
    const data = new CubeData(
      { dimensions: r.dimensions, lons: r.lons, lats: r.lats, depths: r.depths,
        valueRange: r.valueRange },
      f32(r.values), f32(r.seafloor));
    const s = style();
    lastStyle = s;
    const widthM = (r.lons[r.lons.length - 1] - r.lons[0]) * 111_320;
    cube.render(data, { lon0: r.lons[0], lon1: r.lons[r.lons.length - 1], lat0: r.lats[0],
                        lat1: r.lats[r.lats.length - 1], top: 0, bottom: 1000 },
                s, widthM * 0.36);
    legend(s);
    drawCasts();
    notice(null);
    if (fly) aim();
  } catch (e) {
    notice(e instanceof ApiError ? `Nothing to draw for ${state.day}: ${e.message}` : String(e));
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
      name: FIELD_LABEL[k] ?? k, color: color(k === "oceanembed" ? meta.run : k), values: v,
      dash: k === "climatology" ? "2 4" : undefined, width: k === "oceanembed" ? 2.4 : 1.4,
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
  const d = new Date(`${day}T00:00:00Z`);
  $("date").textContent = d.toLocaleDateString("en-GB", { day: "numeric", month: "long",
                                                           year: "numeric", timeZone: "UTC" });
  $("what").textContent = `${FIELD_WHAT[state.field]} · ${state.region}`;
  writeHash();
}

let playing: number | undefined;

async function refreshDay(): Promise<void> {
  setDay(meta.days[+$<HTMLInputElement>("day").value]);
  await Promise.all([drawCube(), drawInputs(), drawEmbedding(), loadCasts()]);
  if (selected?.kind === "cell") await drawProfile();
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
  try {
    const base = await TileMapServiceImageryProvider.fromUrl("/cesium/Assets/Textures/NaturalEarthII");
    const layer = new ImageryLayer(base);
    layer.brightness = 0.55;
    layer.saturation = 0.6;
    viewer.imageryLayers.add(layer);
  } catch { /* the plain ocean-blue globe stands in */ }
  viewer.scene.primitives.add(castLines);
  viewer.scene.primitives.add(castTops);
  cube = new CubeScene(viewer.scene);

  meta = await api.meta();
  if (!meta.days.length) {
    notice("No reconstruction has been written yet. Run python -m oceanembed.predict first.");
    return;
  }
  try { evaluation = await api.evaluation(); } catch { evaluation = undefined; }

  const h = readHash();
  state = {
    day: meta.days.includes(h.day ?? "") ? h.day! : meta.days[Math.min(160, meta.days.length - 1)],
    region: meta.regions[h.region ?? ""] ? h.region! : "Bay of Bengal",
    field: meta.fields.includes(h.field ?? "") ? h.field! : "oceanembed",
    axis: h.axis === "linear" ? "linear" : "stretched",
  };

  const slider = $<HTMLInputElement>("day");
  slider.max = String(meta.days.length - 1);
  slider.value = String(meta.days.indexOf(state.day));
  slider.oninput = () => setDay(meta.days[+slider.value]);
  slider.onchange = () => void refreshDay();
  $("span").textContent = `${meta.days[0]} → ${meta.days[meta.days.length - 1]} · held-out test block`;
  $("play").onclick = play;

  segmented($("regions"), Object.keys(meta.regions).map((r) => [r, r]), state.region, (r) => {
    state.region = r;
    setDay(state.day);
    void drawCube(true);
    drawSkill();
  });
  segmented($("fields"), meta.fields.map((f) => [f, FIELD_LABEL[f] ?? f]), state.field, (f) => {
    state.field = f;
    setDay(state.day);
    void drawCube();
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
  }, ScreenSpaceEventType.LEFT_CLICK);

  setDay(state.day);
  drawSkill();
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
  const b = meta.regions[state.region];
  selected = first ? { kind: "cast", cast: first }
    : { kind: "cell", lat: (b.lat[0] + b.lat[1]) / 2, lon: (b.lon[0] + b.lon[1]) / 2 };
  await drawProfile();
  // A handle for the deck and film capture scripts (submission/capture.cjs, video/capture.cjs):
  // they drive the camera frame by frame and pick a float without a mouse.
  Object.assign(window, { oe: {
    viewer, cube, meta, state: () => state, casts: () => casts,
    ready: true,
    pickCast: async (i: number) => { selected = { kind: "cast", cast: casts[i] }; await drawProfile(); },
    pickCell: async (lat: number, lon: number) => { selected = { kind: "cell", lat, lon }; await drawProfile(); },
    // Camera about the cube, set at once (no flight), and one explicit render.
    orbit: (heading: number, pitch: number, range = 1.9) => {
      const x = cube.extent();
      viewer.camera.viewBoundingSphere(
        new BoundingSphere(Cartesian3.fromDegrees(x.lon, x.lat, x.mid), x.widthM * 0.55),
        new HeadingPitchRange(heading, pitch, x.widthM * range));
      viewer.camera.lookAtTransform(Matrix4.IDENTITY);
      viewer.scene.render();
    },
    setDay: async (day: string) => {
      $<HTMLInputElement>("day").value = String(meta.days.indexOf(day));
      await refreshDay();
    },
  } });
}

void start();
