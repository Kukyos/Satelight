# Portal form: final submission text

The text entered on the SIH portal for the final submission. Every number comes from
`13-eval-results.md` (`data/eval-latest.json`), the same numbers the deck
(`submission/final/Satelight-SIH2026-final.pdf`) and the film use, and every score stands
beside climatology and GLORYS, per basin or for the whole box (hard rule 8).
`python submission/textcheck.py` checks every number in the marked blocks against the
harness, and the length of each field; it fails rather than let a block drift.
Lengths on 2026-10-05: title 94 of 100, abstract 2,952 of 10,000, description 10,462 of
50,000 characters.

## Idea Title (max 100)

<!-- title -->
Satelight: the ocean's temperature down to 1,000 m, every day, from what satellites see on top
<!-- /title -->

## Technology Bucket

AI / Machine Learning (the portal's closest entry).

## Idea Template

`submission/final/Satelight-SIH2026-final.pdf`

## Video

The YouTube link, once uploaded (`26-youtube.md`).

## Abstract / Summary (max 10,000)

<!-- abstract -->
Satellites see the ocean every day, but only its skin: the temperature and saltiness of the surface, the height of the sea, and the currents and winds on it. The heat a cyclone feeds on and the depth where fish gather lie below, where satellites cannot see. Below the surface there are scattered Argo floats, and a reanalysis, GLORYS, that arrives months late.

Satelight rebuilds the ocean's temperature from the surface down to 1,000 m, at the 15 standard depths, every day, on a 0.25° grid over the North Indian Ocean, from eight satellite surface fields alone. An encoder squeezes each point's surface into 32 numbers, the embedding, which is saved every day as a file anyone can open. A decoder turns those numbers into temperature at the 15 depths. Water shallower than a depth is left empty, never filled in. It learned from GLORYS over 2010 to 2020, but never takes GLORYS in.

We check it against 6,144 Argo profiles from 2023 and 2024 that it never saw, at every depth and in each sea, always beside two references: climatology, the long-term average (the floor), and GLORYS, which had already taken these floats in (the ceiling). At the surface over the whole North Indian Ocean its error is 0.54 °C, against 0.87 for climatology and 0.43 for GLORYS. It beats climatology down to 300 m in both the Bay of Bengal and the Arabian Sea, and stays behind GLORYS. The thermocline, around 100 m, is the hardest part, and it runs warm there.

What it is for:
- Cyclone forecasters: the heat a cyclone feeds on, every day. Against the floats over the whole box, climatology misses it by 21.0 kJ/cm², Satelight by 12.9 and GLORYS by 11.9. Cyclone Mocha's cold wake in May 2023 shows up from satellites alone.
- Fishermen: INCOIS's own fishing-zone advisories, each with how deep the warm water goes there, from the latest satellite day. In the Bay of Bengal, climatology misses that depth by 19.3 m, Satelight by 13.7 and GLORYS by 12.0.
- INCOIS: this morning's ocean. On 30 September 2026 GLORYS was 99 days behind, while sea level had arrived the same day and sea temperature a day later. Satelight shows the ocean of days ago, not months.
- Climate research: it rebuilds 1993 to 2000, years when not one Argo float surfaced in this sea. Scored on 2005 to 2009, where floats exist, it beats climatology at every depth and stays behind GLORYS down to 500 m.

Every float keeps its quality flag, data mode and source file, and 8,500 float readings that fail quality control are counted, never dropped. Every number above comes from one test harness in the repository, which anyone can re-run with one command. What is not finished is written down: one encoder's embedding predicts the mixed-layer depth, which it was never trained on, better than the raw inputs (R² 0.351 against 0.255), but no single encoder also sorts the seasons, so that proof is half met.

It runs on one computer with an 8 GB GPU and is open source: github.com/Kukyos/Satelight
<!-- /abstract -->

## Idea Description (max 50,000)

<!-- description -->
The heat that drives a cyclone, the depth that fish follow and the layer a ship's sonar listens through all lie below the sea surface. Satellites measure the surface every day, over the whole ocean, but they cannot see into it. Below the surface, the North Indian Ocean had 3,255 Argo profiles in all of 2023, and the GLORYS reanalysis, the best estimate of the whole water column, arrives months after the day it describes. INCOIS asked for a deep-learning framework that turns surface satellite observations into the temperature below, through a learned embedding, checked against independent Argo floats. Satelight is that framework, working end to end, from the raw satellite files to a 3D viewer.

It reads eight things satellites measure every day: sea surface temperature (OSTIA), sea surface salinity (the multi-observation product), sea level and its anomaly (DUACS), surface currents east and north (OSCAR) and winds east and north (CCMP). Each source is fetched once and put on one common grid, 0.25° and daily, over 45 to 105°E and 5 to 30°N. A finer source is block-averaged onto the grid, and nothing is ever stretched onto a finer one. Every assumption the ingest had to make about a file, a unit or a missing value is written into the data and travels with it into the output. Fetching again reproduces the stored data bit for bit.

The model has two halves. An encoder, a U-Net or a CNN with a transformer, squeezes each point's surface into 32 numbers: the embedding. It is saved every day as a file, so it can be opened, clustered and tested, not just used. A decoder turns those 32 numbers into temperature at the 15 standard depths: 0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700 and 1,000 m. Water shallower than a depth, near a coast or over a shelf, is left empty, never extrapolated. It learned from GLORYS12 over 2010 to 2020; GLORYS is the answer it is taught, never an input. Time is split into blocks that never overlap: training 2010 to 2020, validation 2021 to 2022, test 2023 to 2024. The model is chosen on the validation years alone, before any test number exists. Every run comes from a config file and a seed, repeats bit for bit, and trains on one 8 GB GPU. The output is one NetCDF file per day, in CF conventions, with a list of any day skipped because an input was missing, so a gap is announced and never filled.

The test is Argo floats the model never saw: 6,144 profiles from 2023 and 2024, each compared at its own place and day, depth by depth, in the Bay of Bengal, in the Arabian Sea and over the whole box. Every score sits beside two references. Climatology, the long-term average for that place and day of the year, is the floor: a model that cannot beat it is no use. GLORYS is the ceiling: it had already taken in these very floats, so no satellite-only model should beat it. At the surface the error is 0.54 °C over the whole box, against 0.87 for climatology and 0.43 for GLORYS, which closes 75 percent of the gap between floor and ceiling. In the Bay of Bengal it is 0.35 °C, against 0.64 and 0.26; in the Arabian Sea 0.57 °C, against 0.90 and 0.46. Satelight beats climatology from the surface down to 300 m in both seas and stays behind GLORYS. The thermocline, where temperature drops fastest, is the hard part: at 100 m over the whole box the error is 1.59 °C, against 1.87 for climatology and 1.28 for GLORYS, and the model runs warm there. Below 300 m the ocean barely changes from its average, and all three are within about a tenth of a degree. We also check the INCOIS gridded Argo product before using it as a second reference: it is range-tested and scored against the floats itself, and it agrees with them less well than GLORYS does, so the floats carry the validation and INCOIS is reported beside them with that caveat.

What it is for. Cyclone forecasters read heat, not degrees: a cyclone feeds on water warmer than 26 °C. From every model's 15 levels, and from every float's, we compute the depth of the 20 °C and 26 °C layers and the heat above 26 °C, the tropical cyclone heat potential. Against the floats over the whole box, climatology misses that heat by 21.0 kJ/cm², Satelight by 12.9 and GLORYS by 11.9. In the Bay of Bengal Satelight is level with GLORYS: 13.7 against 13.5, with climatology at 21.1. Cyclone Mocha crossed the Bay in May 2023, inside the test years. From satellites alone, the box's mean heat potential falls from 93.6 to 80.0 kJ/cm² as the storm passes; GLORYS falls from 107.2 to 95.5, and climatology, which knows only the season, rises from 82.9 to 87.6. That is a case study, not a validation, because GLORYS is what the model learned from.

Fishermen. INCOIS already publishes potential fishing zones every day: where fish are likely to gather. Satelight adds how deep the warm water goes in each zone, from the latest satellite day, written in the fisherman's own language (Tamil is shown); the translations still need a native speaker's check. Against held-out floats in the Bay of Bengal, climatology misses the 20 °C depth by 19.3 m, Satelight by 13.7 and GLORYS by 12.0; on average Satelight puts it 9.2 m too deep, which fits its warm thermocline.

This morning's ocean. GLORYS was 99 days behind when we measured on 30 September 2026. Sea level had arrived the same day, sea temperature a day later and salinity six days later. A version of the model that needs only those, four fields in all (temperature, salinity, sea level and its anomaly), runs on the newest satellite day. Against the floats of 24 June to 24 September 2026, 1,086 profiles, most still in real-time mode, it beats climatology down to 150 m over the whole box and in the Bay, but only to 75 m in the Arabian Sea. With all eight fields, which arrive about a month late, it reaches 200 m in both seas. There is no GLORYS for those days to compare with, and that absence is the point of a nowcast.

Before the floats. From 1993 to 2000 not a single Argo profile surfaced in this box, but the satellites were already watching. The same model rebuilds those years, labelled a comparison because salinity before 2010 does not come from a satellite. Scored on 2005 to 2009, years before anything it trained on, against 14,242 profiles, it beats climatology at every depth in both seas and stays behind GLORYS down to 500 m.

Hidden heatwaves. Some marine heatwaves sit 50 to 150 m down, under a surface that looks normal from space. Against the floats, Satelight catches 182 of the 336 hidden warm layers they found, where climatology by definition catches none and GLORYS catches 230. Its skill score is 0.31 against GLORYS's 0.49, and it raises 484 false alarms, which fits its warm thermocline.

The sonar layer, the depth of the mixed layer where a hull sonar's surface duct ends, is not there yet. Over the whole box Satelight misses it by 15.4 m, climatology by 14.4 and GLORYS by 11.5. Only in the Bay of Bengal does it beat climatology: 12.1 m against 12.7, with GLORYS at 11.6.

The viewer shows all of this on a 3D globe in the browser. On the left are the eight satellite fields for the chosen day and the embedding they were squeezed into. In the middle the Bay of Bengal, the Arabian Sea or the whole box stands as a block cut open from the surface to 1,000 m, with the held-out floats of that week standing inside it. A click on a float opens its profile beside Satelight, GLORYS and climatology, always with its quality flag, data mode and source file. Four lenses colour the top of the block by fishing depth, cyclone fuel, the sonar layer and hidden heatwaves. A Dive button peels the sea away level by level, a Now button jumps to the newest satellite day, and the error view shows Satelight minus GLORYS in 3D. The skill panel is read from the test harness, never typed.

How we keep it honest. Every number in the viewer, the deck, the film and this text comes from one harness that anyone can re-run with one command. Every score is shown beside the floor and the ceiling, per depth and per sea, never as one pooled number. Every float reading keeps its quality flag, data mode and source file; 8,500 levels failing quality control are counted, and 165 profiles with no good level are counted as rejected, never quietly dropped. The test years are never touched in training or in choosing the model. Certificate checking is never switched off, and nothing shown is synthetic.

Against the brief, point by point. Preprocessing and harmonisation of multi-source satellite data: built, one fetch per source onto one grid, every assumption recorded. A satellite embedding engine: built, two encoders, and the embedding is a saved daily file. Deep-learning reconstruction at the 15 standard depths: built, exactly those levels, nothing below the sea floor. Validation against independent Argo: built, per depth and per basin, beside climatology and GLORYS, with INCOIS gridded Argo as a second reference. A working proof of concept over the Bay of Bengal and the Arabian Sea: built, the viewer and the daily NetCDF output. A version without currents and winds is scored as an ablation, to measure what those inputs add.

The embedding is judged by two tests fixed before scoring, each against a control that can make it fail: do the daily embeddings sort into the monsoon seasons better than the calendar alone, and does a simple linear probe read the mixed-layer depth, which no model was ever trained on, better from the embedding than from the raw inputs? One encoder's embedding passes the second test (R² 0.351 against 0.255); another passes the first; no single one passes both, so this proof is half met. A third encoder, one never given the calendar, is in training, and will be judged by a rule written down before its training finished.

What is not done yet: that embedding proof, the warm thermocline, the sonar layer, and translations that need a native speaker's check. Each one is written down in the repository with what it would take to close it.

Cost and plan. The data is free and public, the code is open source, and the model trains and runs on one 8 GB GPU. In three months: finish the embedding proof and add salinity at depth. In six: a daily feed for INCOIS. In twelve: the whole Indian Ocean.

There is no public website yet; Satelight runs on the team's computer. The code, the documentation, the film and every measured number are at github.com/Kukyos/Satelight, and with a free Copernicus Marine account the README rebuilds everything from public data.
<!-- /description -->
