// Captions for the YouTube upload:
//   node video/captions.mjs [script.json]   -> submission/youtube/satelight-film.en.srt
//
// Timed from the film itself: each scene starts where the Series in Film.tsx puts it, its
// line starts 0.5 s in, and it lasts as long as the recorded take in public/voice/ (the
// voice src/voice.json says the film plays). Within a take, each sentence gets a share of
// the time by its length. Written from script.json, so a re-voiced or re-timed film needs
// only a re-run.
//
// A guide take (Charlotte's .mp3) must have been read from the text captioned: its hash in
// public/voice/narration.json is checked, and a mismatch fails. When the film was rendered
// from an older script, pass that script (git show <rev>:video/script.json > old.json).
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const script = JSON.parse(readFileSync(process.argv[2] || join(here, 'script.json'), 'utf8'));
const voice = JSON.parse(readFileSync(join(here, 'src', 'voice.json'), 'utf8'));
const narrated = JSON.parse(readFileSync(join(here, 'public', 'voice', 'narration.json'), 'utf8'));
// The guide voice's hash, exactly as narrate.mjs makes it (voice, model, settings, text).
const spoken = (say) => Object.entries(script.speak || {}).filter(([k]) => k !== '_').reduce((t, [k, v]) => t.replaceAll(k, v), say);
const SETTINGS = { stability: 0.45, similarity_boost: 0.75, speed: 1.0 };
const hash = (text) => createHash('sha256').update(`6fZce9LFNG3iEITDfqZZ\neleven_multilingual_v2\n${JSON.stringify(SETTINGS)}\n${text}`).digest('hex').slice(0, 16);
const probe = (f) => Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
const tc = (t) => {
  const ms = Math.round(t * 1000), h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s = Math.floor(ms / 1000) % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`;
};

const cues = [];
let t = 0;
for (const s of script.scenes) {
  const secs = s.clips ? s.clips.reduce((n, c) => n + c.seconds, 0) : s.seconds;
  if (voice[s.id]?.endsWith('.mp3') && narrated[s.id]?.hash !== hash(spoken(s.say)))
    throw new Error(`${s.id}: the guide take was read from other text; pass the script the film was voiced from`);
  const said = voice[s.id] ? probe(join(here, 'public', 'voice', voice[s.id])) : s.say.split(/\s+/).length / script.wordsPerSecond;
  const parts = s.say.match(/[^.!?:]+[.!?:]+(?=\s|$)|[^.!?:]+$/g).map((p) => p.trim()).filter(Boolean);
  const total = parts.reduce((n, p) => n + p.length, 0);
  let at = t + 0.5;
  for (const p of parts) {
    const d = (said * p.length) / total;
    cues.push([at, Math.min(at + d, t + secs), p]);
    at += d;
  }
  t += secs;
}
const out = join(here, '..', 'submission', 'youtube', 'satelight-film.en.srt');
writeFileSync(out, cues.map(([a, b, x], i) => `${i + 1}\n${tc(a)} --> ${tc(b)}\n${x}\n`).join('\n'));
console.log(`${cues.length} cues, film ${t.toFixed(1)} s -> ${out}`);
