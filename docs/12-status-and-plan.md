# Status and plan — 2026-09-28

Where the project stands, how to reproduce it, and what is left before
every requirement in `02-requirements.md` is `done`. No accuracy figures appear here:
they come only from the harness, in `13-eval-results.md`.

## Done

| Piece | Where | Proof |
|---|---|---|
| Ingest of all eight inputs and the target, 2010-02-04 → 2024-12-15, on the 240 × 100 grid | `oceanembed/fetch.py`, `grid.py`, `data/cube/` | `tests/test_cube.py` (grid, daily axis, 15 depths, shelf mask, provenance on every file); `tests/test_reproduce.py --live` (a re-fetch is bit-identical); `tests/test_sources.py --live` (each input equals its source, regridded by hand, on a real day). S1–S3 and E1 are `done` |
| Extended window 1993 → 2009, every source (D-07) | `data/cube/`, `python -m oceanembed.fetch <source> extended` | Same tests |
| Mixed-layer depth 2021–2024, the probe label (never an input) | `data/cube/mld/` | — |
| Argo casts for the test block | `data/cache/argo_erddap/` | QC kept, rejected levels counted |
| Baselines: climatology and per-cell ridge | `oceanembed/baselines.py`, `runs/climatology`, `runs/linear` | `baselines.demo()` |
| Encoders (U-Net, CNN + transformer hybrid), decoder, training | `oceanembed/model.py`, `train.py`, `configs/` | `tests/test_train_repro.py --live`: the same config and seed give a bit-identical run for both encoders |
| Training recipe chosen on the validation block | `configs/dev/` | Reported by the harness under "How the training recipe was chosen" |
| Output writer (daily NetCDF), manifest of skipped days, embedding artefact | `oceanembed/predict.py`, `data/output/` | `tests/test_output.py` |
| Harness: Argo and INCOIS gridded Argo, per depth and basin, beside climatology and GLORYS; INCOIS range test and its own agreement with Argo; validation-only model selection; embedding inspection with controls | `oceanembed/evaluate.py`, `embed.py` | `evaluate.demo()`, `embed.demo()`; the first full report is `13-eval-results.md` (2026-09-28) |
| All five runs trained; headline named on the validation block alone: **hybrid**. *2026-09-28: the rule compares mean validation RMSE in °C, not normalised loss, which is not comparable across absolute and anomaly targets; the hybrid is the headline under both* | `runs/` | Harness, "Model selection" |
| PoC viewer and API (E6) | `viewer/`, `oceanembed/api.py`, `start.bat` / `start.sh` | Reviewed on the hybrid output over both basins, 2026-09-28; `data/figures/viewer_*.jpg` |

What the development runs showed, in words (their figures are in the harness report):

- **Overfitting.** The first models overfit within a few epochs. Eleven training years
  are only about 4,000 strongly correlated days.
- **Warming trend.** The validation years are warmer in the thermocline than the
  training years. GLORYS has no step at its mid-2021 continuation: the warming is
  gradual and sea level rises with it, so the satellite inputs carry the signal.
- **Recipe.** Anomaly target, six epochs, weight decay 1e-2. Crops, dropout, input noise
  and 30 days of input history did not help on the validation block.

What the test block showed, in words (figures in `13-eval-results.md`):

- **Against Argo** the headline (hybrid) beats the climatology floor from the surface
  to 300 m, over the whole box and in each basin, and stays below the GLORYS ceiling.
  From 500 to 700 m it is level with climatology; at 1000 m slightly worse. Not every
  contender clears the floor everywhere: the linear baseline loses to climatology near
  the surface.
- **Thermocline warm bias.** Around 75–150 m the models run warm against Argo. Over the
  whole box and in the Arabian Sea the warm bias is larger than GLORYS's; in the Bay of
  Bengal it is about equal to GLORYS's at 75–100 m and larger only at 125–150 m. It fits
  the warming trend above.
- **INCOIS gridded Argo** agrees with Argo much less well than GLORYS at its own
  resolution (`03-limitations.md` L6). Scored against INCOIS, climatology has the lowest
  RMSE at nearly every depth, ahead of every model and of GLORYS itself, even though
  GLORYS assimilated those Argo floats. The Argo casts are the validation; INCOIS is
  reported beside them with that caveat.
- **Embedding (S4) not met.** Details and the reason in `02-requirements.md` S4.

Data issue found and fixed on the way: CCMP has 18 days with a granule but no daily wind
(one in the main window, 2024-08-31). They are now listed in the provenance as
`empty_days`, the output manifest records the skipped output day, and `test_cube.py`
fails on any empty day that is not logged.

## Reproduce

```
python -m oceanembed.train configs/<run>.toml        # unet, hybrid, unet-abs, hybrid-abs, unet-history,
                                                     # unet-no-currents-winds, unet-extended
python -c "from oceanembed.evaluate import selection; print(selection()['headline'])"
python -m oceanembed.predict hybrid 2023-01-01 2024-12-15
python -m oceanembed.predict <S4 run> 2023-01-01 2024-12-15 --embedding-only
                                                     # when S4 is carried by another run
python -m oceanembed.evaluate                        # writes 13-eval-results.md
start.bat          (or ./start.sh)
```

Run long jobs detached so they survive the terminal closing (`Start-Process` on Windows,
with stdout and stderr to `data/logs/`). Keep the machine plugged in and awake.

## Left before every requirement is `done`

1. **S4 / E2: a different encoder** (D-09), decided 2026-09-28. If it becomes the
   headline, the output, the harness report, the viewer review and the deck are redone,
   so the deck waits for it.
2. **Open ledger items.**
   - D-03: INCOIS LAS endpoint, left deferred (2026-09-28).
   - D-06: measure the salinity reprocessed/real-time join before extending the output
     past 2024-12-15.
3. **Move the project to `G:\Projects\SIH26P4`** once nothing is running. Keep
   `data/cache`. Rebuild `.venv` at the new path; the torch wheel is in `.wheels/`.
4. **Then the deck and the film.** Every figure in them traces to `13-eval-results.md`.
   *2026-09-30: decided with the team to make them now, at idea stage, rather than wait
   for D-09. Deck built (`16-submission.md`); film in `video/` (`21-film.md`). Both say
   S4 is half met, and are redone if D-09 changes the headline. Novelties N1–N3 (gap
   closed, cyclone heat potential vs Argo, cyclone wakes) added to the harness
   (`14-novelties.md`).*

## Disk

About 78 GB, mostly regenerable:

| Folder | What | Needed for |
|---|---|---|
| `data/cache/arco` | Raw Copernicus chunks | Re-running a fetch only |
| `data/cache/glorys025` | GLORYS levels on the grid, per time block | Rebuilding a GLORYS year only |
| `data/cube` | The training cube | Everything |
| `.venv` | Python environment | Everything |
| `.wheels` | The CUDA torch wheel | Rebuilding `.venv` |
