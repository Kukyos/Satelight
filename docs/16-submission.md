# Submission: the idea deck

Six slides in the SIH 2026 template, in the same design as PS 26067's submitted deck
(72/90): its final `.pptx` is the base, and only the words and the pictures change. The
deck presents the project at idea stage: a working prototype, with what is not met yet
stated on the slide (S4, `11-deferred.md` D-09).

```
start.bat                                       # API and viewer on :8026
node submission/capture.cjs                     # viewer screenshots -> submission/figures/shot-*.png
.venv/Scripts/python submission/figures.py      # RMSE chart, logo, crops -> submission/figures/deck-*
python submission/build.py                      # -> submission/final/Satelight-SIH2026.pptx
powershell -ExecutionPolicy Bypass -File submission/topdf.ps1   # -> Satelight-SIH2026.pdf
```

`build.py` needs `python-pptx` and `lxml` (system Python here; not project dependencies).
`submission/base-p3.pptx` is copied from `SIH26P3/submission/sih/final/VVater-SIH2026-final.pptx`
on the first build; `.pptx` files are not committed.

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
| 5 | Users and benefits | Mocha, reconstruction vs GLORYS; Arabian Sea; error view; embedding |
| 6 | 23 references and the repository | — |
