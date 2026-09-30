// Screenshots for the deck, from the running PoC (start.bat: API and viewer on :8026).
// Adapted from SIH26P3 submission/sih/capture.cjs.
//
//   node submission/capture.cjs [shot ...]        (puppeteer-core from video/node_modules)
//
// Headless Chrome, 1600 x 900 at device scale 2. Each shot opens a fresh page on a URL hash
// (day, region, field), waits until no request is in flight, and is saved as
// submission/figures/shot-<name>.png. Crops of the side panels are cut from the same page.
const path = require("path");
const puppeteer = require(path.join(__dirname, "..", "video", "node_modules", "puppeteer-core"));

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.env.VIEWER || "http://127.0.0.1:8026/";
const OUT = path.join(__dirname, "figures");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function settle(page, quiet = 1500, max = 120000) {
  const t0 = Date.now();
  while (Date.now() - t0 < max) {
    const idle = await page.evaluate((q) => window.sl?.ready && performance.now() - (window.__lastNet || 0) > q
      && (window.__inflight || 0) === 0, quiet);
    if (idle) break;
    await sleep(300);
  }
  await page.evaluate(() => window.sl.hq());
  await sleep(2500);   // the fly-to takes 1.6 s
  await page.evaluate(() => window.sl.sharp());
}

async function open(browser, hash) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 2 });
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
  return page;
}

async function shoot(page, name, sel) {
  const file = path.join(OUT, `shot-${name}.png`);
  if (sel) await (await page.$(sel)).screenshot({ path: file });
  else await page.screenshot({ path: file });
  console.log("  ", file);
}

// Choose a float inside the basin with the most accepted levels, so the profile is full.
const pickFullCast = (page) => page.evaluate(async () => {
  const s = window.sl.state(), b = window.sl.meta.regions[s.region];
  let best = -1, n = -1;
  window.sl.casts().forEach((c, i) => {
    if (c.lon < b.lon[0] || c.lon > b.lon[1] || c.lat < b.lat[0] || c.lat > b.lat[1]) return;
    const k = c.obs.filter((v) => v != null).length;
    if (k > n) { n = k; best = i; }
  });
  if (best >= 0) await window.sl.pickCast(best);
  return best;
});

const SHOTS = {
  async hero(b) {
    const p = await open(b, { day: "2023-05-17", region: "Bay of Bengal", field: "satelight", axis: "stretched" });
    const i = await pickFullCast(p); await settle(p, 800);
    // The float's paperwork, for the slide caption (hard rule 2: never shown without it).
    const cast = await p.evaluate((i) => { const c = window.sl.casts()[i];
      return { platform: c.platform, cycle: c.cycle, day: c.day, data_mode: c.data_mode,
               levels_rejected: c.levels_rejected, source_file: c.source_file }; }, i);
    require("fs").writeFileSync(path.join(OUT, "shot-profile.json"), JSON.stringify(cast, null, 1));
    await shoot(p, "hero"); await shoot(p, "hero-view", "#view"); await shoot(p, "profile", "#right");
    await shoot(p, "left", "#left");
    await p.close();
  },
  async arabian(b) {
    const p = await open(b, { day: "2023-06-18", region: "Arabian Sea", field: "satelight", axis: "stretched" });
    await pickFullCast(p); await settle(p, 800);
    await shoot(p, "arabian"); await shoot(p, "arabian-view", "#view"); await p.close();
  },
  async glorys(b) {
    const p = await open(b, { day: "2023-05-17", region: "Bay of Bengal", field: "glorys", axis: "stretched" });
    await shoot(p, "glorys-view", "#view"); await p.close();
  },
  async error(b) {
    const p = await open(b, { day: "2024-05-20", region: "Arabian Sea", field: "error", axis: "stretched" });
    await shoot(p, "error"); await shoot(p, "error-view", "#view"); await p.close();
  },
  // A day with no reconstruction (an input is missing): the viewer must say so, not fill it.
  async skipped(b) {
    const p = await open(b, { day: "2024-08-31", region: "Bay of Bengal", field: "satelight", axis: "stretched" });
    await shoot(p, "skipped"); await p.close();
  },
};

(async () => {
  const want = process.argv.slice(2);
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: "new",
    args: ["--use-angle=d3d11", "--enable-gpu-rasterization", "--ignore-gpu-blocklist"] });
  try {
    for (const [name, fn] of Object.entries(SHOTS)) {
      if (want.length && !want.includes(name)) continue;
      console.log(name);
      await fn(browser);
    }
  } finally { await browser.close(); }
})();
