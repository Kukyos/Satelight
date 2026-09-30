// The render in segments, so a browser crash costs one segment, not the film.
//
//   node render.mjs        check, video in 1,500-frame segments (kept between runs),
//                          audio once, then joined into out/oceanembed-film-raw.mp4
//
// A segment that exists is not rendered again; delete out/seg to start over.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';

const run = (cmd, args) => execFileSync(cmd, args, { stdio: 'inherit', shell: process.platform === 'win32' });
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
  run('ffmpeg', ['-y', '-loglevel', 'error', '-i', `${f}.tmp.mp4`, '-c', 'copy', f]);
}
if (!existsSync('out/seg/audio.wav')) run('npx', ['remotion', 'render', 'Film', 'out/seg/audio.wav', '--codec=wav', '--log=warn']);
writeFileSync('out/seg/list.txt', parts.map((p) => `file '${basename(p)}'`).join(String.fromCharCode(10)));
run('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'out/seg/list.txt', '-i', 'out/seg/audio.wav',
  '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', 'out/oceanembed-film-raw.mp4']);
console.log('wrote out/oceanembed-film-raw.mp4');
