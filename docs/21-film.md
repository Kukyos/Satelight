# The film

A film of the running prototype, **5 min 45 s**, cut in code with Remotion, in the
same grammar as PS 26067's film: near-black cards with one idea each, footage of the
viewer with lower thirds, one narrator (ElevenLabs' **Charlotte**) reading every line. The
accent is the viewer's own yellow.

It renders as two copies with the same picture and timing: `video/out/satelight-film.mp4`
with the narration and `video/out/satelight-film-no-voice.mp4` without it.

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
```

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
| Opening | `open`, `title`, `brief` | The Bay of Bengal after Mocha, orbiting; the title; the brief's own sentence |
| Why and how | `sparse`, `inputs`, `pipeline` | floats vs satellites; the eight fields; the pipeline to the embedding and 15 depths |
| The viewer | `fields`, `axis`, `floats`, `qc` | reconstruction, GLORYS, climatology, error; √ and linear depth; a held-out float; the counts |
| What the floats say | `rmse`, `gap`, `heat` | RMSE by depth per basin; share of the gap closed; heat potential |
| Cyclones | `mocha`, `mocha-card`, `biparjoy` | days stepped through each storm; the harness's wake maps and numbers |
| Limits | `error`, `reference`, `embedding` | the error view; INCOIS checked; the embedding, half met |
| Close | `whole`, `arabian`, `evidence`, `notyet`, `end` | the whole box; measured tiles and the command; what is not done; the repository |

## Checks before it ships

- [ ] `npm run check` passes: numbers, pacing, every clip at its length.
- [ ] Watched once, end to end, with sound.
