# Requirements — every "shall", what satisfies it, and what proves it

Each line of `01-problem-statement.md` that asks for something, mapped to the thing we
build and the check that shows it is done. A requirement is not done until its check
exists and passes. Status is updated in the same pass as the work.

Status: `—` not started · `wip` · `done` (check passes) · `blocked` (see `11-deferred.md`)

## The seven "shall" items

| # | Requirement (from the text) | Deliverable | Proof | Status |
|---|---|---|---|---|
| S1 | Preprocessing and harmonization pipeline for multi-source satellite and ocean datasets | One fetch function per source, one regrid step onto the common grid, one daily cube writer | Re-running the pipeline for one day reproduces the stored cube bit-for-bit; every normalisation it made is in the provenance record | done — `oceanembed/fetch.py`; all eight inputs and the target 2010–2024, plus 1993–2009 (D-07); `tests/test_reproduce.py --live` passes (2026-09-28) |
| S2a | Standardize to 0.25° × 0.25° | Common grid: DUACS's 0.25° lattice (cell centres at x.125), 45–105°E × 5–30°N, 240 × 100 cells | Assertion that every stored variable has exactly those coordinates | done — `tests/test_cube.py` passes on every stored file (2026-09-28) |
| S2b | Standardize to daily | CCMP 6-hourly → daily mean; everything else is already daily | Assertion on the time axis: one step per calendar day, no gaps unless logged | done — `tests/test_cube.py` passes; missing days are listed in each file's provenance |
| S3a | Input: SST | OSTIA, 0.05° → 0.25° by 5 × 5 block mean | Block mean vs source mean over the box agrees to float tolerance | done — `tests/test_sources.py --live` (2015-06-15) |
| S3b | Input: SSS | MULTIOBS SSS (moi-00051), 0.125° → 0.25° by 2 × 2 block mean | Same | done — `tests/test_sources.py --live` (2015-06-15) |
| S3c | Input: SSH / SLA | DUACS twosat (moi-00145) `sla` and `adt`, native 0.25° | Pass-through check: values identical to source | done — `tests/test_sources.py --live`, `sla` and `adt` (2015-06-15): identical up to float32 storage rounding, under 1e-7 m |
| S3d | Input: currents U, V | OSCAR L4 final v2.0, 0.25° centred on the quarter degree, shifted half a cell onto the lattice | Each common cell equals the mean of the four surrounding OSCAR cells on one real day. *Amended 2026-09-28: the row said native and pass-through; OSCAR sits half a cell off the lattice, so it is interpolated and labelled so (`03-limitations.md` L4).* | done — `tests/test_sources.py --live` (2015-06-15) |
| S3e | Input: winds U, V | CCMP v3.1, 0.25° 6-hourly → daily mean | Daily mean of four synoptic times checked on one known day | done — `tests/test_sources.py --live` (2015-06-15) |
| S4 | Compact satellite embeddings from a DL architecture (CNN / ViT / AE / GNN / attention hybrid) | Encoder that maps a surface patch to a fixed-length latent vector; the embedding is a saved, inspectable artefact, not only a hidden layer | Embeddings for held-out days cluster by known regime (monsoon season), beating a day-of-year-only control; a linear probe recovers mixed-layer depth, never trained on, better than the same probe on the raw inputs — measured, not asserted. *Amended 2026-09-28: eddy polarity was dropped as a proof because it is defined by sea level anomaly, which is itself an input, so recovering it from the embedding would show nothing.* *Amended 2026-09-28 (second): the season test is clustering (NMI) against the day-of-year control; nearest-neighbour agreement is still reported, judged against chance. Measured on the validation block (hybrid, unet and an absolute-target run): 93–99.7 % of each day's nearest neighbour lies 4–7 days away, just past the ±3-day exclusion, so near each calendar season boundary it falls in the neighbouring season, while the day-of-year control matches the same date a year apart (0.996). No embedding of a smoothly varying ocean can clear that control without encoding the calendar, which is what the control exists to catch. Also decided: S4 may be carried by a labelled candidate that is not the headline. It is chosen on the validation block alone (the MLD probe fitted on 2021 and scored on 2022) and inspected on the test block beside the headline.* | wip — `model.py` (unet, hybrid); inspection in `embed.py`. **Not met on the 2026-09-28 harness run** (`13-eval-results.md`, Embedding inspection): the daily embedding clusters by season better than the day-of-year control on NMI, but its nearest-neighbour agreement falls below that control, and the mixed-layer-depth probe on the embedding scores below the same probe on the raw inputs. *Observation, not an amendment: seasons are defined by calendar date, so the day-of-year nearest-neighbour control is close to perfect by construction.* A different encoder is to be tried (`11-deferred.md` D-09). |
| S5 | Train reconstruction models from surface state to temperature profiles | Decoder / head mapping the embedding to 15 depth values per cell | Training is reproducible from a seed and a config file, bit for bit (`tests/test_train_repro.py --live`); loss curves saved | done — `tests/test_train_repro.py --live` passes for both encoders (2026-09-28); loss curves in `runs/<run>/history.json` |
| S6a | Temperature at 0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m | Output variable with exactly those 15 levels | Assertion on the depth axis; cells shallower than a level are masked, never extrapolated | done — `tests/test_output.py` on the written output and `tests/test_cube.py` on the target (2026-09-28) |
| S7 | Evaluate with independent observations: correlation, RMSE, bias | Eval harness writing `docs/13-eval-results.md` and `data/eval-latest.json` | The harness runs end to end; every number in the deck traces to it | done — `python -m oceanembed.evaluate` runs end to end and writes `13-eval-results.md` and `data/eval-latest.json` (2026-09-28): Argo per depth and basin, INCOIS gridded Argo with its own agreement with Argo shown. Against INCOIS, climatology beats every model and GLORYS at nearly every depth (`03-limitations.md` L6), so the Argo casts carry the validation |

## The six Expected Solution bullets

| # | Expected | Covered by | Status |
|---|---|---|---|
| E1 | End-to-end preprocessing pipeline for satellite and ocean datasets | S1–S3 | done |
| E2 | Satellite embedding engine learning latent ocean representations | S4 | wip |
| E3 | DL reconstruction model for subsurface temperature | S5, S6 | done |
| E4 | Standardized output, daily, 0.25° | S2, S6 — the reconstruction is written on the common grid as a daily NetCDF | done |
| E5 | Validation framework using independent ARGO observations | S7, with the independence limits in `03-limitations.md` L1 | done |
| E6 | Working PoC over the Bay of Bengal / Arabian Sea | Trained over the full North Indian Ocean box; demonstrated in a viewer over both basins, with the Argo casts in the same scene | done — reviewed 2026-09-28 on the headline (hybrid) output: both basins render from `data/output/daily`, the Argo casts and skill panel come from the harness output, each cast shows its data mode, rejected-level count and source file, and a day with no reconstruction (2024-08-31) is announced, not filled. Screenshots: `data/figures/viewer_*.jpg`. Redone if D-09 changes the headline |

## What "independent" has to mean here

The problem statement asks for validation against *independent* Argo observations. Every
recommended training dataset has already seen Argo in some form (`03-limitations.md` L1).
The minimum honest design, recorded here so it is not diluted later:

1. **Time-blocked hold-out.** The last contiguous block of the common window is never
   seen in training or model selection. Argo profiles in that block are the test set.
2. **Three numbers, not one.** On the same test profiles, report:
   - *climatology* — the floor any model must beat;
   - *our reconstruction*;
   - *GLORYS itself* — the ceiling, since GLORYS assimilated those profiles.
3. **Per depth, not pooled.** Every metric is reported at each of the 15 levels. A pooled
   RMSE hides the thermocline, where the error lives.
4. **Per basin.** Bay of Bengal and Arabian Sea separately, because the problem statement
   names both and their stratification differs.
