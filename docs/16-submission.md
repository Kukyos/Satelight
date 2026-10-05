# Submission: the idea deck

Six slides in the SIH 2026 template, in the same design as PS 26067's deck: only the words
and the pictures change. The deck presents the project at idea stage: a working
prototype, with what is not met yet stated on the slide (S4, `11-deferred.md` D-09).

**Final submission (2026-10-05): `final/Satelight-SIH2026-final.pdf`.** It is built on
PS 26067's deck as hand-edited for the finals (`vvaterref.pptx` in the repo root, not
committed): the amber scheme (headings `AE630C`, the slide-3 title `4E2F0A`, amber rules,
roadmap and benefit boxes), the team-name footer removed, and Team ID **187550** on the
title page. The earlier `final/Satelight-SIH2026.pdf` (navy, 2026-09-30) is kept and not
edited. Beside the restyle, three things the prototype gained after 2026-09-30 are on the
slides, each read from the harness:

- slide 2: "This morning's ocean", the nowcast, with how far behind GLORYS was when measured
  (in place of "The reference is checked too", which stays in `14-novelties.md` N4);
- slide 4: the roadmap's NOW reads "prototype, nowcast";
- slide 5: the Fisheries tile shows the fishing-depth lens over the Arabian Sea, with that
  basin's 20 °C-depth RMSE beside climatology and GLORYS.

```
start.bat                                       # API and viewer on :8026
node submission/capture.cjs                     # viewer screenshots -> submission/figures/shot-*.png
.venv/Scripts/python submission/figures.py      # RMSE chart, logo, crops -> submission/figures/deck-*
python submission/build.py                      # -> submission/final/Satelight-SIH2026-final.pptx
powershell -ExecutionPolicy Bypass -File submission/topdf.ps1 -name Satelight-SIH2026-final
python submission/textcheck.py                  # the portal and YouTube text (below)
```

`build.py` needs `python-pptx` and `lxml` (system Python here; not project dependencies).
Its shape names were written against the submitted P3 deck, `submission/base-p3.pptx`,
copied from `SIH26P3/submission/sih/final/VVater-SIH2026-final.pptx` on the first build.
The finals deck renumbered its shapes, so `translate()` finds each one again by position
and size (its groups' too), else by its text; the roadmap and the sustainability box were
rebuilt by hand and are mapped by name (`MOVED`). A text box the hand edit shrank around
P3's shorter words gets its old width back. `.pptx` files are not committed.

The text for the portal is `25-portal-form.md`; the YouTube title, description, chapters,
tags, thumbnails and captions are `26-youtube.md`.

## The rules the deck keeps

- **Every number is read from `data/eval-latest.json`.** `build.py` types none.
- **Every claim about a score is asserted before the deck is written.** "Beats
  climatology from the surface to 300 m in both basins and stays behind GLORYS", "the
  thermocline runs warm", "S4 is half met": if a new harness run falsifies one, the build
  fails instead of printing it.
- **Scores appear only per depth and basin, beside climatology and GLORYS** (hard rule 8):
  the slide-4 chart is RMSE by depth for the whole box and each basin, with both. The
  four tiles are counts, plus the heat-potential RMSE shown as climatology → ours with
  GLORYS beside it.
- **Every picture is a capture of the running build or a harness figure**, cropped to the
  frame's aspect before it is swapped in, never stretched.

## What each slide carries

| Slide | Content | Pictures |
|---|---|---|
| 1 | Title page, from `01-problem-statement.md` | — |
| 2 | Proposed solution; the expected solution point by point; innovation (`14-novelties.md`) | the Bay of Bengal after Mocha; a float's profile; Mocha's wake |
| 3 | Three-layer architecture: viewer, pipeline and model, public data | tech marks from the P3 deck |
| 4 | Harness counts, RMSE by depth, challenges and strategies, roadmap | `deck-rmse.png` |
| 5 | Users and benefits | Mocha, reconstruction vs GLORYS; the fishing-depth lens, Arabian Sea; error view; embedding |
| 6 | 23 references and the repository | — |

## Link check, 2026-10-05

Every URL on slide 6 was fetched with `curl -L` and a browser user agent. All returned 200,
the repository and the problem-statement link included, except the two NASA PO.DAAC pages
(OSCAR, CCMP): `podaac.jpl.nasa.gov` refused the connection from this network (port 443
timed out). Both collections answer by their short names in NASA's CMR catalogue
(`cmr.earthdata.nasa.gov/search/collections.json?short_name=...`), so the links are kept;
re-check them from another network.
