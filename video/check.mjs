// Adapted from SIH26P3 video/check.mjs.
// Run before every render (`npm run render` does). Fails when:
//
//   - a number said or shown in script.json is not in data/eval-latest.json at the precision
//     written, and not in script.json's `sourced` list with where it comes from;
//   - a line is too long for its scene at the reading pace (script.json wordsPerSecond);
//   - a clip is missing or is not the length script.json gives it;
//   - a recorded line in public/voice/ runs longer than its scene.
//
// It also writes src/voice.json, the recorded lines the film should play.
import { readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync, copyFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const script = JSON.parse(readFileSync(join(here, 'script.json'), 'utf8'));
// The harness writes Python's NaN for an empty band; JSON has no NaN, so it becomes null.
// The film reads the cleaned copy, src/eval.json, written here before anything can fail.
const evalJson = JSON.parse(readFileSync(join(here, '..', 'data', 'eval-latest.json'), 'utf8').replace(/\bNaN\b/g, 'null'));
writeFileSync(join(here, 'src', 'eval.json'), JSON.stringify(evalJson));
const probe = (f) => {
  try { return Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f], { stdio: 'pipe' }).toString()); }
  catch { return NaN; } // still being written, or broken
};

let failures = 0;
const fail = (m) => { failures++; console.log(' FAIL ', m); };

// ------------------------------------------------------------------ numbers
// Every number in the harness output, and every number inside its strings (dates, bands).
const known = [];
(function walk(x) {
  if (typeof x === 'number') known.push(x);
  else if (typeof x === 'string') for (const m of x.matchAll(/\d+(?:\.\d+)?/g)) known.push(Number(m[0]));
  else if (x && typeof x === 'object') Object.values(x).forEach(walk);
})(evalJson);
// The cyclone boxes and dates, as config.CYCLONES defines them; and the harness figures the
// cards show, copied into public/img so the render needs nothing outside video/.
const config = readFileSync(join(here, '..', 'satelight', 'config.py'), 'utf8');
const cyc = config.slice(config.indexOf('CYCLONES = {'), config.indexOf('# ----', config.indexOf('CYCLONES = {')));
for (const m of cyc.matchAll(/\d+(?:\.\d+)?/g)) known.push(Number(m[0]));
mkdirSync(join(here, 'public', 'img'), { recursive: true });
for (const s of script.scenes) if (s.image) copyFileSync(join(here, '..', 'data', 'figures', s.image), join(here, 'public', 'img', s.image));
const sourced = new Set(Object.keys(script.sourced).filter((k) => k !== '_').map((k) => k.replace(/,/g, '')));

const inHarness = (tok) => {
  const d = (tok.split('.')[1] || '').length, v = Number(tok);
  return known.some((k) => Number(Math.abs(k).toFixed(d)) === v);
};

console.log('numbers');
let counted = 0;
for (const s of script.scenes) {
  // The brief's quote is verbatim and carries no numbers of ours.
  const texts = [s.say, s.lower, ...(s.lowers || []), s.cite, ...(s.lines || [])].filter(Boolean);
  for (const t of texts)
    for (const m of t.matchAll(/(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])/g)) {
      const tok = m[0].replace(/,/g, '').replace(/\.$/, '');
      counted++;
      if (!inHarness(tok) && !sourced.has(tok)) fail(`${s.id}: "${m[0]}" is not in eval-latest.json or script.json sourced  (… ${t.slice(Math.max(0, m.index - 30), m.index + 20)} …)`);
    }
}
console.log(`  ${counted} numbers checked`);

// ------------------------------------------------------------------ claims in words
// What the narration says in words, checked against the harness, so a new run cannot make
// the film say something false. Mirrors the asserts in submission/build.py.
{
  const D = evalJson.depths, at = (d) => D.indexOf(d);
  const HEADK = `${evalJson.selection.headline} (selected)`;
  const R = ['North Indian Ocean (whole box)', 'Bay of Bengal', 'Arabian Sea'];
  const col = (tab, reg, pick) => tab[reg][Object.keys(tab[reg]).find(pick)].map((s) => s.rmse);
  const claim = (ok, what) => { if (!ok) fail(`claim no longer true: ${what}`); };
  const pf = evalJson.prefloat.argo;
  for (const r of R) {
    const o = col(pf, r, (k) => k.includes('before the floats')), cl = col(pf, r, (k) => k === 'climatology'),
      g = col(pf, r, (k) => k === 'GLORYS (ceiling)');
    claim(o.every((v, i) => v < cl[i]), `prefloat beats climatology at every depth, ${r}`);
    claim(D.every((d, i) => d > 500 || o[i] > g[i]), `prefloat behind GLORYS down to 500 m, ${r}`);
  }
  const nf = evalJson.nowcast.tiers.fast.argo, nl = evalJson.nowcast.tiers.full.argo;
  const beatsTo = (tab, r, depth) => {
    const o = col(tab, r, (k) => k.startsWith('nowcast')), cl = col(tab, r, (k) => k === 'climatology');
    return D.every((d, i) => d > depth || o[i] < cl[i]);
  };
  const loses = (tab, r, depth) => {
    const o = col(tab, r, (k) => k.startsWith('nowcast')), cl = col(tab, r, (k) => k === 'climatology');
    return o[at(depth)] > cl[at(depth)];
  };
  claim(beatsTo(nf, R[0], 150) && beatsTo(nf, R[1], 150), 'four-field nowcast beats climatology to 150 m, box and Bay');
  claim(beatsTo(nf, R[2], 75) && loses(nf, R[2], 100), 'four-field nowcast, Arabian Sea: to 75 m only');
  claim(R.every((r) => beatsTo(nl, r, 200)), 'eight-field nowcast beats climatology to 200 m');
  claim(R.every((r) => D.every((d, i) => d > 300 ||
    col(evalJson.argo, r, (k) => k === HEADK)[i] < col(evalJson.argo, r, (k) => k === 'climatology')[i])),
    'test block: beats climatology to 300 m in every region');
  const mld = evalJson.hazard['MLD (m)'][R[0]];
  claim(mld[HEADK].rmse > mld.climatology.rmse, 'sonar layer: not better than climatology over the whole box');
  const bay = evalJson.hazard['MLD (m)'][R[1]];
  claim(bay[HEADK].rmse < bay.climatology.rmse, 'sonar layer: better than climatology in the Bay (the not-yet card)');
  console.log('\nclaims checked');
}

// ------------------------------------------------------------------ pace, clips, voice
const wps = script.wordsPerSecond;
const voiceDir = join(here, 'public', 'voice');
const recorded = existsSync(voiceDir) ? readdirSync(voiceDir) : [];
const voice = {};
let total = 0;
console.log('\nscenes');
for (const s of script.scenes) {
  const secs = s.clips ? s.clips.reduce((n, c) => n + c.seconds, 0) : s.seconds;
  const words = s.say.split(/\s+/).filter(Boolean).length;
  // A recorded line is measured; an unrecorded one is estimated at the reading pace.
  const v = recorded.find((f) => f.replace(/\.(wav|mp3|m4a)$/i, '') === s.id);
  const said = v ? probe(join(voiceDir, v)) : NaN;
  const need = v ? said + 0.5 + 0.5 : words / wps + 1;
  const mm = `${Math.floor(total / 60)}:${String(Math.floor(total % 60)).padStart(2, '0')}`;
  console.log(`  ${mm}  ${s.id.padEnd(12)} ${String(secs).padStart(4)} s  ${String(words).padStart(3)} words  ${v ? `${said.toFixed(1)} s recorded` : `~${need.toFixed(1)} s to say`}`);
  if (need > secs) fail(`${s.id}: the line needs ~${need.toFixed(1)} s${v ? ` (recorded, ${said.toFixed(1)} s from 0.5 s in)` : ` at ${wps} words/s`}; the scene is ${secs} s`);
  for (const c of s.clips || []) {
    const f = join(here, 'public', 'clips', `${c.name}.mp4`);
    if (!existsSync(f)) { fail(`${s.id}: clip ${c.name}.mp4 not recorded (node capture.cjs ${c.name})`); continue; }
    const d = probe(f);
    if (!(Math.abs(d - c.seconds) <= 0.05)) fail(`${s.id}: ${c.name}.mp4 is ${d.toFixed(2)} s, script.json says ${c.seconds} (re-run node capture.cjs ${c.name})`);
  }
  if (v) voice[s.id] = v;
  total += secs;
}
writeFileSync(join(here, 'src', 'voice.json'), JSON.stringify(voice, null, 2) + '\n');

// The reading copy: what to say, when, over what. Written from script.json so it cannot drift.
{
  const tc = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  const out = ['# The film: the script to read', '',
    'Generated by `node video/check.mjs` from `video/script.json`. **Do not edit here**; edit the',
    'JSON and re-run. How the film is built, and the rules it keeps: `21-film.md`.', '',
    `Runtime **${tc(total)}**. Each line has time to spare at ${wps} words a second. Record one file per`,
    'scene, named for the scene (`video/public/voice/tilt.wav`), and it plays from the start of that scene.', ''];
  let t = 0, act = null;
  for (const s of script.scenes) {
    const secs = s.clips ? s.clips.reduce((n, c) => n + c.seconds, 0) : s.seconds;
    if (s.act && s.act !== act) { out.push(`## ${s.act}`, ''); act = s.act; }
    const shows = s.card ? `card: ${s.card}` : s.clips.map((c) => c.name).join(', ');
    out.push(`### ${tc(t)} · \`${s.id}\` · ${secs} s`, '', `*On screen: ${shows}.*${s.lower ? ` ${s.lower}.` : ''}`, '', `> ${s.say}`, '');
    t += secs;
  }
  writeFileSync(join(here, '..', 'docs', '21-film-script.md'), out.join('\n'));
}
console.log(`\n  runtime ${Math.floor(total / 60)}:${String(Math.round(total % 60)).padStart(2, '0')} · ${Object.keys(voice).length} of ${script.scenes.length} lines recorded`);

// --soft: report but do not stop (the studio opens on a half-recorded film).
if (failures) { console.log(`\n${failures} failed`); process.exit(process.argv.includes('--soft') ? 0 : 1); }
console.log('\nall checks pass');
