# Requirements — every "shall", what satisfies it, and what proves it

Each line of `01-problem-statement.md` that asks for something, mapped to the thing we
build and the check that shows it is done. A requirement is not done until its check
exists and passes. Status is updated in the same pass as the work.

Status: `—` not started · `wip` · `done` (check passes) · `blocked` (see `11-deferred.md`)

## The seven "shall" items

| # | Requirement (from the text) | Deliverable | Proof | Status |
|---|---|---|---|---|
| S1 | Preprocessing and harmonization pipeline for multi-source satellite and ocean datasets | One fetch function per source, one regrid step onto the common grid, one daily cube writer | Re-running the pipeline for one day reproduces the stored cube bit-for-bit; every normalisation it made is in the provenance record | wip — `oceanembed/fetch.py`; fetch running |
| S2a | Standardize to 0.25° × 0.25° | Common grid: DUACS's 0.25° lattice (cell centres at x.125), 45–105°E × 5–30°N, 240 × 100 cells | Assertion that every stored variable has exactly those coordinates | wip — `grid.py` stencils, checked by `grid.demo()` |
| S2b | Standardize to daily | CCMP 6-hourly → daily mean; everything else is already daily | Assertion on the time axis: one step per calendar day, no gaps unless logged | wip — CCMP daily mean in `_read_ccmp` |
| S3a | Input: SST | OSTIA, 0.05° → 0.25° by 5 × 5 block mean | Block mean vs source mean over the box agrees to float tolerance | wip — fetched 2010; rest running |
| S3b | Input: SSS | MULTIOBS SSS (moi-00051), 0.125° → 0.25° by 2 × 2 block mean | Same | wip — fetched 2010–2024 |
| S3c | Input: SSH / SLA | DUACS twosat (moi-00145) `sla` and `adt`, native 0.25° | Pass-through check: values identical to source | wip — fetched 2010–2024 |
| S3d | Input: currents U, V | OSCAR L4 final v2.0, native 0.25° | Pass-through check | wip — OPeNDAP subset, fetch running (D-01 resolved) |
| S3e | Input: winds U, V | CCMP v3.1, 0.25° 6-hourly → daily mean | Daily mean of four synoptic times checked on one known day | wip — OPeNDAP subset, fetch running (D-01 resolved) |
| S4 | Compact satellite embeddings from a DL architecture (CNN / ViT / AE / GNN / attention hybrid) | Encoder that maps a surface patch to a fixed-length latent vector; the embedding is a saved, inspectable artefact, not only a hidden layer | Embeddings for held-out days cluster by known regime (monsoon season), beating a day-of-year-only control; a linear probe recovers mixed-layer depth, never trained on, better than the same probe on the raw inputs — measured, not asserted. *Amended 2026-09-28: eddy polarity was dropped as a proof because it is defined by sea level anomaly, which is itself an input, so recovering it from the embedding would show nothing.* | wip — `model.py` (unet, hybrid); inspection in `embed.py` |
| S5 | Train reconstruction models from surface state to temperature profiles | Decoder / head mapping the embedding to 15 depth values per cell | Training is reproducible from a seed and a config file, bit for bit (`tests/test_train_repro.py --live`); loss curves saved | wip — `train.py` + `configs/` |
| S6a | Temperature at 0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000 m | Output variable with exactly those 15 levels | Assertion on the depth axis; cells shallower than a level are masked, never extrapolated | wip — `_fetch_glorys` + `predict.py` |
| S7 | Evaluate with independent observations: correlation, RMSE, bias | Eval harness writing `docs/13-eval-results.md` and `data/eval-latest.json` | The harness runs end to end; every number in the deck traces to it | wip — `evaluate.py` |

## The six Expected Solution bullets

| # | Expected | Covered by | Status |
|---|---|---|---|
| E1 | End-to-end preprocessing pipeline for satellite and ocean datasets | S1–S3 | wip |
| E2 | Satellite embedding engine learning latent ocean representations | S4 | wip |
| E3 | DL reconstruction model for subsurface temperature | S5, S6 | wip |
| E4 | Standardized output, daily, 0.25° | S2, S6 — the reconstruction is written on the common grid as a daily NetCDF | wip |
| E5 | Validation framework using independent ARGO observations | S7, with the independence limits in `03-limitations.md` L1 | wip |
| E6 | Working PoC over the Bay of Bengal / Arabian Sea | Trained over the full North Indian Ocean box; demonstrated in a viewer over both basins, with the Argo casts in the same scene | wip |

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
