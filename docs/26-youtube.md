# YouTube upload

Everything needed to put the film on YouTube. The file is `video/out/satelight-film.mp4`
(6:13, 1920 × 1080, 30 fps, H.264), the render of 2026-09-30 with the guide narration.
Upload it as it is.

**The render's narration is the script of commit `21e32a3`**, not the current
`video/script.json`: the script was rewritten afterwards (`1f512e2`) for the team's own
recording, and only the spoken lines changed, not one scene's length. So the chapters below
hold for both, and the captions are made from the script the render was voiced from:

```
git show 21e32a3:video/script.json > voiced.json
node video/captions.mjs voiced.json     # -> submission/youtube/satelight-film.en.srt
```

`captions.mjs` checks each guide take's hash in `video/public/voice/narration.json`
against the text it captions and fails on a mismatch, so the captions cannot drift from the
audio. If the team's recording replaces the guide voice and the film is re-rendered, run it
with no argument, and re-run `textcheck.py`, which checks the chapters against the scene
times.

Every number in the description is harness output, and every score stands beside
climatology and GLORYS (hard rule 8). `python submission/textcheck.py` checks the numbers,
the lengths and the chapters.

---

## Title (max 100)

<!-- yt-title -->
```
Satelight: The Ocean Below, Seen from Space | SIH 2026 · PS 26066 (INCOIS) | Team Null
```
<!-- /yt-title -->

## Thumbnail

Three 1920×1080 JPEGs in `submission/youtube/`, all under YouTube's 2 MB cap. None shows a
float (hard rule 2: a float is never shown without its QC flag), and the one number on them
is harness output.

| File | Picture | Words |
|---|---|---|
| `thumbnail-a.jpg` | The dive at 0:47: the Bay of Bengal on 17 May 2023, cut open | THE OCEAN BELOW, FROM SPACE · Temperature to 1,000 m, from satellites alone |
| `thumbnail-b.jpg` | 15 November 1997 at 3:38: the whole North Indian Ocean, before any Argo float surfaced there | BEFORE THE ARGO FLOATS · 1997 REBUILT · From satellites alone, to 1,000 m |
| `thumbnail-c.jpg` | The dive at 0:47 | THE REANALYSIS ARRIVES 99 DAYS LATE · Satelight reads this week's satellites |

`b` is the strongest picture and the most surprising claim; the film explains it at 3:31.
`a` says what the product is at a glance. `c` is the sharpest hook: 99 days is how far
behind GLORYS was on 2026-09-30 (`13-eval-results.md`, Nowcast), the same figure the film
shows at 3:01.

They are laid out in `submission/youtube/thumbnail.html` (Anton and Inter from Google
Fonts) and rendered by `node submission/youtube/render.cjs`, which pulls the frames out of
the film with ffmpeg, renders each variant in headless Chrome and deletes the frames
afterwards. Change the wording in the HTML and re-run.

## Description

Paste everything between the fences. YouTube rejects `<` and `>` in descriptions, so the
text uses neither. The first two lines are what shows before "...more".

<!-- yt-description -->
```
Satellites see only the top of the ocean. Satelight rebuilds its temperature down to 1,000 m, every day, from that surface alone, and checks it against Argo floats it never saw.
Source code, documents and every measured number: https://github.com/Kukyos/Satelight

Smart India Hackathon 2026, problem statement SIH26066 from INCOIS (Ministry of Earth Sciences): a satellite embedding-based deep learning framework for reconstructing subsurface ocean temperature from surface satellite observations. Team Null, team ID 187550.

What it does
• Eight satellite surface fields in (sea surface temperature, salinity, sea level and its anomaly, currents and winds), temperature at the 15 standard depths to 1,000 m out, every day, at 0.25°, over the North Indian Ocean.
• An encoder squeezes each point's surface into 32 numbers, the embedding, saved every day as a file. A decoder turns it into the 15 depths. Water shallower than a depth is left empty, never filled in.
• Checked against 6,144 Argo profiles from 2023 and 2024 that it never saw. At the surface over the whole box its error is 0.54 °C, against 0.87 for climatology (the floor) and 0.43 for GLORYS (the ceiling, which had already taken these floats in). It beats climatology down to 300 m in both seas.
• Cyclone fuel, the heat above 26 °C, every day. Against the floats, climatology misses it by 21.0 kJ/cm², Satelight by 12.9 and GLORYS by 11.9.
• Fishing depth beside INCOIS's own fishing zones. In the Bay of Bengal, climatology misses the 20 °C depth by 19.3 m, Satelight by 13.7 and GLORYS by 12.0.
• This morning's ocean: GLORYS was 99 days behind on 30 September 2026. Satelight reads the satellites of days ago.
• Before the floats: 1993 to 2000 rebuilt, years when no Argo float surfaced in this sea.
• Every float keeps its quality flag, data mode and source file. Readings that fail quality control are counted, never dropped.

Not done yet, and said so in the film: the embedding proof is half met, the thermocline runs warm, and the sonar layer is not there yet.

Every number in this film comes from one test harness in the repository, and anyone can re-run it with one command.

Chapters
0:00 Satellites see only the surface
0:44 The dive: surface to 1,000 m
1:00 What the satellites give it
1:15 How it works
1:35 How deep to fish, in their own language
2:16 Cyclone fuel: Cyclone Mocha
2:47 This morning's ocean
3:31 Before the floats
4:08 Hidden heatwaves
4:37 The sonar layer
4:54 Checked against held-out floats
5:07 What the floats say
5:24 The embedding
5:44 Measured, and what is not done yet

Built with PyTorch, xarray and FastAPI on the server, CesiumJS, TypeScript and Vite in the browser, and Remotion for the film. Data: Copernicus Marine (GLORYS12, OSTIA, multi-observation salinity, DUACS sea level), NASA PO.DAAC (OSCAR currents, CCMP winds), Argo via Ifremer, INCOIS ERDDAP, IMD.

#SIH2026 #SmartIndiaHackathon #INCOIS #Oceanography #DeepLearning
```
<!-- /yt-description -->

## Tags

Paste as one comma-separated line (under YouTube's 500-character limit):

<!-- yt-tags -->
```
Satelight, Smart India Hackathon, SIH 2026, SIH26066, INCOIS, ocean temperature, subsurface temperature, deep learning, satellite oceanography, Argo floats, Bay of Bengal, Arabian Sea, North Indian Ocean, GLORYS, Copernicus Marine, cyclone heat potential, Cyclone Mocha, PyTorch, CesiumJS, Ministry of Earth Sciences
```
<!-- /yt-tags -->

## Settings

| Field | Value |
|---|---|
| Visibility | **Unlisted** for submission. Anyone with the link can watch, but it is not in search. Switch to Public after judging if you want it found. |
| Audience | No, it's not made for kids |
| Category | Science & Technology |
| Video language / caption language | English (India) |
| Captions | Upload `submission/youtube/satelight-film.en.srt` as English. The film has no burned-in subtitles, and YouTube's auto-captions mishear Satelight, INCOIS and GLORYS. The Tamil line at 1:50 is captioned in Tamil, as it is spoken. |
| Altered or synthetic content | No. The footage is the running viewer on real data. The guide narration is a synthetic voice that does not imitate any real person, which YouTube's disclosure does not cover. |
| License | Standard YouTube License |
| Allow embedding | On, so the link plays inside the portal and slides |
| Comments | On, sorted by Top |
| End screen | The end card runs 6:06 to 6:13, long enough for one "Subscribe" element; optional. |
| Recording date / location | Leave blank |

## Pinned comment

Post this from the channel after the upload and pin it:

```
Code, documents and the test harness behind every number: https://github.com/Kukyos/Satelight
Chapters are in the description. Questions about the data or the method are welcome here.
```

## Before sharing the link

- Watch the uploaded version once at 1080p and check the chapters show up on the progress
  bar. YouTube needs the first chapter at 0:00, at least three chapters, and each one at
  least 10 s long; `textcheck.py` checks all three against the scene times in
  `video/script.json`. A scene starting on a half second gets the next whole second, so a
  chapter never opens on the last frames of the scene before.
- Check the captions line up with the voice in YouTube's caption editor.
- Put the YouTube link in `25-portal-form.md` under Video.
