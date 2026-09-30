# SIH 2026 · PS 26066 — Satelight

INCOIS / Ministry of Earth Sciences. Category: Software. Theme: Disaster Management.

## The 30-second version

Reconstruct the ocean's temperature from the surface down to 1000 m, every day, at 0.25°,
over the North Indian Ocean (45–105°E, 5–30°N), **from satellite surface observations
alone**: SST, salinity, sea level, currents and winds. A deep network compresses each
day's surface state into an embedding, and a second network decodes that embedding into a
15-level temperature profile at every cell. The result is scored against held-out Argo
floats, beside climatology (the floor) and the GLORYS reanalysis (the ceiling), at every
depth and in each basin.

## The files

| File | What's in it | When to read |
|---|---|---|
| `01-problem-statement.md` | The official text, verbatim, with the dataset table. `ps-26066-incois.pdf` is the original. | First, and whenever scope is argued about. |
| `02-requirements.md` | Every "shall" and every expected-solution bullet, with its deliverable and its proof. | Before starting any piece of work; update the status when it's done. |
| `03-limitations.md` | The structural limits, and the constraint each one forces. | Before designing anything. L1 (independence) and L2 (splits) decide whether the results mean anything. |
| `05-data-sources.md` | Every source, and how far each was actually checked. | Before writing an ingest path or quoting a dataset. |
| `06-method.md` | The design, step by step, and why each choice was made. | Before changing the pipeline or the model. |
| `12-status-and-plan.md` | What is done, what was interrupted, the exact commands to resume, and what is left. | At the start of every session. |
| `10-unsourced.md` | Values we are using without a source. | Before quoting any value. |
| `11-deferred.md` | Everything knowingly incomplete, with what it blocks. | The live status doc. |
| `13-eval-results.md` | Generated numbers. Never hand-edited. | Whenever an accuracy claim is questioned. |
| `14-novelties.md` | What the project does beyond the brief, each with its harness numbers. | Before pitching it. |
| `16-submission.md` | How the idea deck is built, and the rules it keeps. | Before rebuilding the deck. |
| `21-film.md`, `21-film-script.md` | How the film is built; the script with timecodes (generated). | Before re-cutting or re-recording it. |

## Built on PS 26067

PS 26067 (`Desktop/SIH26P3`, the 3D ocean visualisation platform) already solved the
data-access and validation half of this problem. Code is **copied** from there with a
header noting where it came from, never imported across the two repositories. P3 is not
edited while working on this project.

| P3 module | What it does there | What it becomes here |
|---|---|---|
| `server/ocean/arco.py` | Opens Copernicus ARCO Zarr stores directly and reads only the chunks needed | The fetch path for GLORYS (target) and, if they open the same way, OSTIA, SSS and DUACS (D-04) |
| `server/ocean/cf.py` | Defensive CF normalisation that records every change it makes | Unchanged in purpose: every source goes through it |
| `server/ocean/argo.py`, `argo_global.py` | Argo profiles over HTTPS and ERDDAP, adjusted-first, QC kept, pressure → depth with TEOS-10 | The independent-validation reader |
| `server/ocean/colocate.py` | Puts a gridded field and a float profile on the same axes, with the depth sign pinned by physics | Scoring reconstruction vs Argo, per profile |
| `server/ocean/residual.py` | Observed-minus-model binned onto the grid, never interpolated into empty cells | Error maps of reconstruction minus Argo, per depth |
| `server/eval/run_eval.py` | The harness that writes `13-eval-results.md` and its JSON | The same discipline; new metrics |
| `server/ocean/certs/` + truststore | TLS for INCOIS's incomplete chain, with verification on | Reused as is for the INCOIS ERDDAP |
| `viewer/` (Cesium) | 3D volume of an ocean field, Argo casts in the same scene | The PoC demo: reconstruction vs GLORYS vs Argo, in 3D |

What is **new** here, with no counterpart in P3: the training-cube builder, the
embedding encoder, the profile decoder, the training loop, the embedding inspection, and
the PO.DAAC fetchers (OSCAR, CCMP).

## Plan of work

1. **Ingest.** One `_fetch_*` per source. Common-grid regrid (L4). Per-year daily cubes
   on disk, with provenance. Start with SST, SSS, SSH and the GLORYS target, which need
   no new login.
2. **Baselines before models.** Climatology, then linear regression per level, scored by
   the harness. These set the bar and prove the harness works.
3. **Encoder + decoder.** A CNN / U-Net encoder over surface patches makes the embedding,
   and an MLP head decodes 15 levels per cell. Then one attention-based variant, compared
   by the harness, not by feel.
4. **Validation.** Held-out Argo per depth and per basin, the GLORYS ceiling, and INCOIS
   gridded Argo at 1°.
5. **Embedding inspection** (L10).
6. **PoC.** The reconstruction in the viewer over the Bay of Bengal and the Arabian Sea,
   the daily NetCDF output, the deck and the film.

## Working defaults

- Region 45–105°E / 5–30°N. Grid: the DUACS 0.25° lattice, 240 × 100.
- Output: 15 levels, 0–1000 m, daily.
- Python venv at `.venv`. PyTorch for the models. xarray, `copernicusmarine`, `gsw`.
- Machine: RTX 4060 8 GB, 32 GB RAM (L8).
