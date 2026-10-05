# The film

A film of the running prototype, about **6 min 15 s**, cut in code with Remotion, in the
same grammar as PS 26067's long film (not its abandoned short cut): a cinematic open,
an index of what is coming, near-black cards with one idea each, footage of the viewer
with lower thirds. The accent is the viewer's own yellow.

**The voice is the team's.** Each scene's line is recorded by a team member, one file per
scene. ElevenLabs' Charlotte reads every line first (`npm run narrate`), only as a guide
track: it sets each scene's length (`narrate.mjs --fit`) and shows the pace. A team
recording replaces it by taking its name: `video/public/voice/<scene>.wav` (or `.m4a`),
with the guide's `<scene>.mp3` deleted. `npm run check` then measures the real takes and
fails any scene a take overruns; lengthen that scene in `script.json` and re-run.

It renders as two copies with the same picture and timing: `video/out/satelight-film.mp4`
with whatever voice is in `public/voice/`, and `video/out/satelight-film-no-voice.mp4`
without it, for recording against.

The script to read, with timecodes, is **`21-film-script.md`**, generated from
`video/script.json` by `node video/check.mjs`, so it cannot drift from the cut.

## The rules the film keeps

- **No number the harness did not produce.** Every number said or shown in
  `script.json` is matched by `check.mjs` against `data/eval-latest.json` at the
  precision written. A number that is not harness output is listed under `sourced` with
  where it comes from (the 15 depths, the 0.25° grid, the training years, the cyclone
  boxes in `config.CYCLONES`). The cards draw their numbers from the JSON
  (`video/src/data.ts`) and never type them.
- **Scores only beside the floor and the ceiling.** The RMSE card draws climatology,
  GLORYS and Satelight per depth, for the whole box and each basin; the heat-potential
  card does the same per basin.
- **Floats appear with their QC.** The float scene shows the panel's quality flag, data
  mode and source file; the next card gives the rejected-level count.
- **Honest about the gaps.** The embedding card says S4 is half met; the `notyet` card
  names the embedding proof, the warm thermocline, INCOIS's own portal and the years after
  2024.
- **The cyclone scenes are case studies, not validation**, and the card says so: GLORYS
  is the training target.
- **Nothing is synthetic.** Every frame of footage is the running viewer reading the
  pipeline's own output.

## How it is made

```
start.bat                        # API and viewer on :8026
cd video
npm install
npm run narrate                  # Charlotte reads what changed; each scene is sized to its line
node capture.cjs                 # every clip -> public/clips/*.mp4 (about 10 minutes)
npm run check                    # numbers, pacing, clip lengths; writes 21-film-script.md
npm run studio                   # preview
npm run render                   # check, render in segments (render.mjs), then both copies
node captions.mjs [script.json]  # YouTube captions, timed from the takes (26-youtube.md)
```

The end card carries the team's portal ID, 187550. It read K26125 until 2026-10-05, when
only the last segment was re-rendered to correct it; the other segments and the narration
are the render of 2026-09-30, unchanged.

`capture.cjs` opens the viewer headless at 1920 × 1080, sets the camera for each frame
through the viewer's capture handle (`window.sl.orbit`), renders the scene once and
photographs it, piping frames into ffmpeg (30 fps, H.264 CRF 16). Day steps and field
switches wait for their data on the real clock between frames, so a load is shorter in the
film than it was. Clip lengths come from `script.json`, and `check.mjs` fails if a clip
does not match.

`render.mjs` renders the picture in 1,500-frame segments, kept between runs, builds the
sound with ffmpeg (the narration is the only sound: each line half a second into its scene,
as `Film.tsx` places it), and joins them. A segment that crashes the headless browser is retried, and a
re-run renders only what is missing. Inter is served from `public/fonts/` (the latin
variable file from `@fontsource-variable/inter`) as a plain `@font-face`, so a render never
waits on a font server. A `FontFace().load()` wrapped in `delayRender()` never settled
inside the render tabs and timed the render out, so the font is not awaited that way.

`narrate.mjs` needs `ELEVENLABS_API_KEY` in `.env` (never committed). A line re-renders
only when its text or the voice changes; the mp3s in `public/voice/` are committed, so a
render needs no credits. `speak` in `script.json` holds how a word is said (Satelight,
GLORYS, INCOIS, kJ/cm²).

## The cut

| Act | Scenes | On screen |
|---|---|---|
| Opening | `open`, `title`, `index`, `brief` | the planet from space with that day's satellite SST, down to the Bay (cinema mode, no panels); the title; nine looping chapter tiles; the brief's own sentence |
| The dive | `dive` | orbit to 1,000 m, the cube peeled level by level, the gauge and NOAA's light zones |
| How it works | `inputs`, `pipeline` | the eight fields; the pipeline to the embedding and 15 depths |
| How deep to fish | `fishing`, `tamil`, `fishing-score` | the nowcast day with INCOIS's zones; one advisory in Tamil; the 20 °C depth against Argo |
| Cyclone fuel | `cyclone`, `heat` | Mocha stepped day by day on IMD's track; heat potential against Argo |
| This morning's ocean | `now`, `latency`, `nowcast-rmse` | the Now button; measured delays; RMSE by depth on real-time floats (no GLORYS: it does not reach those days) |
| Before the floats | `prefloat`, `floats`, `prefloat-rmse` | November 1997; Argo profiles per year; RMSE by depth on 2005–2009, beside GLORYS |
| Hidden heatwaves | `heatwave`, `hidden` | the heatwave lens; detections against Argo |
| The sonar layer | `sonar` | the mixed-layer lens, and that it is not there yet |
| Checked | `check`, `rmse`, `embedding` | a held-out float; RMSE by depth on the test block; the embedding, half met |
| Close | `evidence`, `notyet`, `end` | measured tiles and the command; what is not done; the repository |

`check.mjs` also asserts every claim the narration makes in words (beats climatology to
150 m, behind GLORYS down to 500 m, not better at the sonar layer, and so on) against the
harness output, so a new harness run cannot leave the film saying something false.

## Checks before it ships

- [ ] `npm run check` passes: numbers, pacing, every clip at its length.
- [ ] Watched once, end to end, with sound.
