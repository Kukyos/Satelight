// The film's footage, recorded frame by frame from the running PoC (start.bat, :8026).
// Adapted from SIH26P3 video/capture.cjs, much reduced: this viewer has no particle
// animation, so no virtual clock is needed; the camera is set per frame and the scene
// rendered once before each photograph, so a slow GPU never makes the motion stutter.
//
//   node capture.cjs              every clip in script.json
//   node capture.cjs bay-orbit    or just some
//
// Each clip is exactly script.json's seconds at 30 fps, rendered at 3840 x 2160 (device
// scale 2, 4x MSAA, every tile loaded before each photograph) and downscaled with Lanczos
// to 1920 x 1080, H.264 CRF 14, into
// public/clips/<name>.mp4. Waits for data (a day change, a field switch) happen on the
// real clock between frames, so a load is shorter in the film than it was. Nothing on
// screen is staged: every field, float and panel is what the API returned.
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const puppeteer = require("puppeteer-core");

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.env.VIEWER || "http://127.0.0.1:8026/";
const OUT = path.join(__dirname, "public", "clips");
const FPS = 30;
const script = JSON.parse(fs.readFileSync(path.join(__dirname, "script.json"), "utf8"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => t * t * (3 - 2 * t);

async function settle(page, quiet = 900, max = 90000) {
  const t0 = Date.now();
  while (Date.now() - t0 < max) {
    const idle = await page.evaluate((q) => window.sl?.ready && performance.now() - (window.__lastNet || 0) > q
      && (window.__inflight || 0) === 0, quiet);
    if (idle) return;
    await sleep(150);
  }
}

async function open(browser, hash) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 2 });
  await page.evaluateOnNewDocument(() => {
    const f = window.fetch;
    window.__inflight = 0;
    window.fetch = async (...a) => {
      window.__inflight++; window.__lastNet = performance.now();
      try { return await f(...a); } finally { window.__inflight--; window.__lastNet = performance.now(); }
    };
  });
  page.on("pageerror", (e) => console.log("  page error:", e.message));
  await page.goto(`${BASE}#${new URLSearchParams(hash)}`, { waitUntil: "load" });
  await settle(page);
  await page.evaluate(() => window.sl.hq());
  await sleep(2200);   // the opening fly-to is 1.6 s
  return page;
}

const orbit = (page, h, p = -0.36, r = 1.9) => page.evaluate((h, p, r) => window.sl.orbit(h, p, r), h, p, r);
const clickIn = (page, host, label) => page.evaluate((host, label) => {
  [...document.querySelectorAll(`#${host} button`)].find((b) => b.textContent === label).click();
}, host, label);
const pickFull = (page) => page.evaluate(async () => {
  const s = window.sl.state(), b = window.sl.meta.regions[s.region];
  let best = -1, n = -1;
  window.sl.casts().forEach((c, i) => {
    if (c.lon < b.lon[0] || c.lon > b.lon[1] || c.lat < b.lat[0] || c.lat > b.lat[1]) return;
    const k = c.obs.filter((v) => v != null).length;
    if (k > n) { n = k; best = i; }
  });
  if (best >= 0) await window.sl.pickCast(best);
});
const daysBetween = (a, b) => {
  const out = [];
  for (let d = new Date(`${a}T00:00:00Z`); d <= new Date(`${b}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + 1))
    out.push(d.toISOString().slice(0, 10));
  return out;
};

// Each clip: the page it opens on, and what happens at frame f of n (t = f / n).
const BAY = { day: "2023-05-17", region: "Bay of Bengal", field: "satelight", axis: "stretched" };
const ARAB = { day: "2023-06-18", region: "Arabian Sea", field: "satelight", axis: "stretched" };
function stepper(first, last) {
  const days = daysBetween(first, last);
  let shown = -1;
  return async (page, t) => {
    const k = Math.min(days.length - 1, Math.floor(t * days.length));
    if (k !== shown) { shown = k; await page.evaluate((d) => window.sl.setDay(d), days[k]); await settle(page, 300); }
    await orbit(page, 0.42);
  };
}
function lensStepper(first, last, lensHash) {
  const days = daysBetween(first, last);
  let shown = -1;
  return async (page, t) => {
    const k = Math.min(days.length - 1, Math.floor(t * days.length));
    if (k !== shown) { shown = k; await page.evaluate((d) => window.sl.setDay(d), days[k]); await settle(page, 300); }
    await orbit(page, lerp(0.30, 0.55, t), -0.42, 1.8);
  };
}
const NOW = "2026-09-24";
const CLIPS = {
  // The planet from space, painted with that day's satellite SST and lit by the real sun,
  // turning to the Indian Ocean, then down to the Bay.
  "globe-open": {
    hash: { ...BAY, cinema: "1" },
    frame: (p, t) => {
      const u = ease(t);
      return orbit(p, lerp(-1.25, 0.42, u), lerp(-1.45, -0.38, u), 11 * Math.pow(1.9 / 11, u));
    },
  },
  // From orbit down to the Bay: the first quarter of the Dive, then a slow turn.
  "globe-descend": {
    hash: BAY,
    frame: async (p, t) => {
      if (t < 0.7) await p.evaluate((u) => window.sl.diveAt(u), (t / 0.7) * 0.2199);
      else { await p.evaluate(() => window.sl.endDiveQuiet && window.sl.endDiveQuiet()); await orbit(p, lerp(0.42, 0.62, (t - 0.7) / 0.3), -0.36, lerp(1.9, 1.75, (t - 0.7) / 0.3)); }
    },
  },
  // The sea peeled away level by level, surface to 1,000 m.
  "dive": { hash: { ...BAY, cinema: "1" }, frame: (p, t) => p.evaluate((u) => window.sl.diveAt(u), 0.22 + 0.78 * t) },
  "fishing-now": {
    hash: { ...BAY, day: NOW, lens: "fishing" },
    frame: (p, t) => orbit(p, lerp(0.20, 0.60, ease(t)), -0.46, lerp(1.8, 1.55, ease(t))),
  },
  "cyclone-mocha": { hash: { ...BAY, day: "2023-05-06", lens: "cyclone" }, frame: lensStepper("2023-05-06", "2023-05-17") },
  "cyclone-biparjoy": { hash: { ...ARAB, day: "2023-06-05", lens: "cyclone" }, frame: lensStepper("2023-06-05", "2023-06-17") },
  "heatwave-orbit": {
    hash: { ...BAY, day: "2023-03-15", lens: "heatwave" },
    frame: (p, t) => orbit(p, lerp(0.15, 0.65, ease(t)), -0.5, 1.75),
  },
  "sonar-orbit": {
    hash: { day: "2023-07-15", region: "North Indian Ocean", field: "satelight", axis: "stretched", lens: "sonar" },
    frame: (p, t) => orbit(p, lerp(0.1, 0.45, ease(t)), -0.62, 1.45),
  },
  "now-jump": {
    hash: { ...BAY, day: "2024-09-24" },
    frame: (() => {
      let done = false;
      return async (p, t) => {
        if (!done && t > 0.35) { done = true; await p.evaluate(() => document.getElementById("now").click()); await settle(p, 400); }
        await orbit(p, lerp(0.35, 0.55, t));
      };
    })(),
  },
  "prefloat-orbit": {
    hash: { day: "1997-11-15", region: "North Indian Ocean", field: "satelight", axis: "stretched" },
    frame: (p, t) => orbit(p, lerp(0.5, 0.1, ease(t)), -0.6, 1.45),
  },

  "bay-orbit": { hash: BAY, frame: (p, t) => orbit(p, lerp(0.05, 0.85, ease(t)), lerp(-0.30, -0.40, t)) },
  "fields": {
    hash: BAY,
    frame: (() => {
      const order = ["Reconstruction", "GLORYS", "Climatology", "Error"];
      let shown = 0;
      return async (p, t) => {
        const k = Math.min(3, Math.floor(t * 4));
        if (k !== shown) { shown = k; await clickIn(p, "fields", order[k]); await settle(p, 300); }
        await orbit(p, 0.42);
      };
    })(),
  },
  "float-click": {
    hash: BAY,
    frame: (() => {
      let done = false;
      return async (p, t) => {
        if (!done && t > 0.25) { done = true; await pickFull(p); }
        await orbit(p, lerp(0.42, 0.62, ease(t)), -0.36, lerp(1.9, 1.55, ease(t)));
      };
    })(),
  },
  "mocha-days": { hash: { ...BAY, day: "2023-05-03" }, frame: stepper("2023-05-03", "2023-05-20") },
  "arabian-orbit": { hash: ARAB, frame: (p, t) => orbit(p, lerp(0.85, 0.15, ease(t))) },
  "biparjoy-days": { hash: { ...ARAB, day: "2023-06-02" }, frame: stepper("2023-06-02", "2023-06-19") },
  "error-orbit": {
    hash: { day: "2024-05-20", region: "Arabian Sea", field: "error", axis: "stretched" },
    frame: (p, t) => orbit(p, lerp(0.15, 0.75, ease(t)), -0.38),
  },
  "whole-orbit": {
    hash: { day: "2023-07-15", region: "North Indian Ocean", field: "satelight", axis: "stretched" },
    frame: (p, t) => orbit(p, lerp(0.1, 0.5, ease(t)), -0.62, 1.45),
  },
  "linear-depth": {
    hash: ARAB,
    frame: (() => {
      let done = false;
      return async (p, t) => {
        if (!done && t > 0.4) { done = true; await clickIn(p, "axis", "Linear depth"); await settle(p, 300); }
        await orbit(p, 0.42);
      };
    })(),
  },
};

async function record(browser, name, seconds) {
  const clip = CLIPS[name];
  if (!clip) throw new Error(`no clip called ${name} in capture.cjs`);
  const page = await open(browser, clip.hash);
  const n = Math.round(seconds * FPS);
  const file = path.join(OUT, `${name}.mp4`);
  const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS),
    "-i", "-", "-vf", "scale=1920:1080:flags=lanczos", "-c:v", "libx264", "-crf", "14",
    "-preset", "slow", "-pix_fmt", "yuv420p", "-r", String(FPS), file]);
  const t0 = Date.now();
  for (let f = 0; f < n; f++) {
    await clip.frame(page, f / n);
    await page.evaluate(() => window.sl.sharp());
    const buf = await page.screenshot({ type: "jpeg", quality: 94 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
  }
  ff.stdin.end();
  await new Promise((r) => ff.on("close", r));
  await page.close();
  console.log(`  ${name}: ${n} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const want = process.argv.slice(2);
  const clips = script.scenes.flatMap((s) => s.clips || []);
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new",
    args: ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"] });
  try {
    for (const c of clips) {
      if (want.length && !want.includes(c.name)) continue;
      await record(browser, c.name, c.seconds);
    }
  } finally { await browser.close(); }
})();
