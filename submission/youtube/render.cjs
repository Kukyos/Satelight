// Adapted from SIH26P3 submission/youtube/render.cjs.
// Renders the YouTube thumbnails from frames of the film.
//   node submission/youtube/render.cjs        -> thumbnail-a.jpg, -b.jpg, -c.jpg (1920x1080)
// Needs Chrome and ffmpeg; puppeteer-core is borrowed from video/node_modules.
const path = require("path");
const fs = require("fs");
const { execFileSync } = require("child_process");
const { pathToFileURL } = require("url");
const puppeteer = require("../../video/node_modules/puppeteer-core");

const DIR = __dirname;
const FILM = path.join(DIR, "..", "..", "video", "out", "satelight-film.mp4");
const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
// Frames with no float on screen (hard rule 2: a float is never shown without its QC):
// the dive's first second, the Bay cut open (0:47), and 15 November 1997, the whole North
// Indian Ocean before any Argo float surfaced there (3:38). thumbnail.html fades out each
// frame's captions and panels.
const FRAMES = { "dive.png": 47, "prefloat.png": 218 };

for (const [name, t] of Object.entries(FRAMES)) {
  const out = path.join(DIR, name);
  execFileSync("ffmpeg", ["-v", "error", "-y", "-ss", String(t), "-i", FILM, "-frames:v", "1", out]);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, args: ["--allow-file-access-from-files"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  for (const v of ["a", "b", "c"]) {
    await page.goto(pathToFileURL(path.join(DIR, "thumbnail.html")).href + "?v=" + v, { waitUntil: "networkidle0" });
    await page.evaluate(() => document.fonts.ready);
    const png = path.join(DIR, `thumbnail-${v}.png`);
    await page.screenshot({ path: png });
    // YouTube caps thumbnails at 2 MB; a q2 JPEG of this lands well under.
    execFileSync("ffmpeg", ["-v", "error", "-y", "-i", png, "-q:v", "2", path.join(DIR, `thumbnail-${v}.jpg`)]);
    fs.unlinkSync(png);
  }
  await browser.close();
  for (const name of Object.keys(FRAMES)) fs.unlinkSync(path.join(DIR, name));
  for (const v of ["a", "b", "c"]) {
    const kb = fs.statSync(path.join(DIR, `thumbnail-${v}.jpg`)).size / 1024;
    if (kb > 2000) throw new Error(`thumbnail-${v}.jpg is ${kb.toFixed(0)} KB, over YouTube's 2 MB`);
    console.log(`thumbnail-${v}.jpg ${kb.toFixed(0)} KB`);
  }
})();
