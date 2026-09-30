// The render in segments, so a browser crash costs one segment, not the film.
//
//   node render.mjs        check, video in 1,500-frame segments (kept between runs),
//                          audio once, then joined into out/oceanembed-film-raw.mp4
//
// A segment that exists is not rendered again; delete out/seg to start over.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';

// Only npx needs a shell on Windows; ffmpeg must not get one, or cmd.exe eats the | and ; in
// the filter graph.
const run = (cmd, args) => execFileSync(cmd, args,
  { stdio: 'inherit', shell: cmd === 'npx' && process.platform === 'win32' });
run('node', ['check.mjs']);
const { TOTAL } = JSON.parse(execFileSync('node', ['-e',
  "const s=require('./script.json');let n=0;for(const x of s.scenes)n+=Math.round(30*(x.clips?x.clips.reduce((a,c)=>a+c.seconds,0):x.seconds));console.log(JSON.stringify({TOTAL:n}))"]).toString());
const SEG = 1500;
mkdirSync('out/seg', { recursive: true });
const parts = [];
for (let a = 0; a < TOTAL; a += SEG) {
  const b = Math.min(TOTAL, a + SEG) - 1;
  const f = join('out', 'seg', `v-${String(a).padStart(6, '0')}-${b}.mp4`);
  parts.push(f);
  if (existsSync(f)) { console.log(`have ${f}`); continue; }
  for (let tries = 1; ; tries++) {
    try { run('npx', ['remotion', 'render', 'Film', `${f}.tmp.mp4`, `--frames=${a}-${b}`, '--muted', '--log=warn']); break; }
    catch (e) { if (tries >= 3) throw e; console.log(`segment ${a}-${b} failed, retrying (${tries})`); }
  }
  renameSync(`${f}.tmp.mp4`, f);   // only a finished segment gets its real name
}
// The sound is the narration alone: each scene's line from half a second into the scene, as
// Film.tsx places it. Built with ffmpeg because remotion.config's CRF rejects audio codecs.
{
  const voice = JSON.parse(readFileSync('src/voice.json', 'utf8'));
  const script = JSON.parse(readFileSync('script.json', 'utf8'));
  const inputs = [], delays = [];
  let at = 0;
  for (const s of script.scenes) {
    const frames = Math.round(30 * (s.clips ? s.clips.reduce((n, c) => n + c.seconds, 0) : s.seconds));
    if (voice[s.id]) {
      inputs.push('-i', join('public', 'voice', voice[s.id]));
      const ms = Math.round((at + 15) / 30 * 1000);
      delays.push(`[${delays.length}:a]adelay=${ms}|${ms}[a${delays.length}]`);
    }
    at += frames;
  }
  const mix = delays.map((_, i) => `[a${i}]`).join('') + `amix=inputs=${delays.length}:normalize=0,apad=whole_dur=${(TOTAL / 30).toFixed(3)}[out]`;
  run('ffmpeg', ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', `${delays.join(';')};${mix}`,
    '-map', '[out]', '-ar', '48000', '-ac', '2', 'out/seg/audio.wav']);
}
writeFileSync('out/seg/list.txt', parts.map((p) => `file '${basename(p)}'`).join(String.fromCharCode(10)));
run('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'out/seg/list.txt', '-i', 'out/seg/audio.wav',
  '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', 'out/oceanembed-film-raw.mp4']);
console.log('wrote out/oceanembed-film-raw.mp4');
