# OceanEmbed — subsurface ocean temperature from satellite surface observations

Smart India Hackathon 2026 · Problem Statement 26066 · INCOIS, Ministry of Earth Sciences.

Daily, 0.25°, 15-level (0–1000 m) temperature over the North Indian Ocean (45–105°E,
5–30°N), reconstructed from satellite SST, salinity, sea level, currents and winds
through a learned embedding, and validated against held-out Argo floats.

Start with [`docs/00-start-here.md`](docs/00-start-here.md). Every accuracy figure is in
[`docs/13-eval-results.md`](docs/13-eval-results.md), which only the harness writes.

## How it works

```
 OSTIA SST ─┐
 SSS (SMOS/SMAP era) ─┤      common 0.25° grid        encoder              decoder
 DUACS ADT, SLA ─┤  ──►  240 × 100, daily,   ──►  U-Net or CNN +   ──►  per-cell MLP  ──►  15 depths
 OSCAR currents ─┤      provenance on every   transformer: a          (0 … 1000 m),
 CCMP winds ─┘      file                     32-number embedding      shelf masked
                                             per cell per day
```

- **Target:** GLORYS12 reanalysis temperature, block-averaged conservatively onto the
  grid and interpolated to the 15 standard depths between the two native levels that
  bracket each one. Cells shallower than a level are masked, never extrapolated.
- **Inputs:** satellite surface observations and static fields only. Nothing from GLORYS
  goes in.
- **Splits:** contiguous blocks. Train 2010-02 → 2020, validation 2021-02 → 2022-11,
  test 2023-01 → 2024-12. The test block is never used in training or model selection.
- **Validation:** every core Argo cast in the test block, compared at its own cell and
  day, per depth and per basin, beside climatology (the floor) and GLORYS (the ceiling).
  Also INCOIS gridded Argo at its own 1° / 10-day resolution.
- **The embedding is a product:** saved per cell per day, and inspected. Does it
  separate the monsoon seasons? Does it hold mixed-layer depth, which it was never
  trained on?

## Run it

```
python -m venv .venv  (Python 3.13)  &&  pip install -r requirements.txt
python -m oceanembed.fetch static
python -m oceanembed.fetch all                 # resumable; long on a slow link
python -m oceanembed.argo --period test
python -m oceanembed.baselines                 # climatology + per-cell ridge
python -m oceanembed.train configs/unet.toml
python -m oceanembed.train configs/hybrid.toml
python -m oceanembed.predict unet 2023-01-01 2024-12-15   # daily NetCDF + embeddings
python -m oceanembed.evaluate                  # writes docs/13-eval-results.md
start.bat   (or ./start.sh)                    # the PoC viewer at http://127.0.0.1:8026
python -m pytest tests                         # every module's self-check
```

Credentials: Copernicus Marine in `.env` (`COPERNICUSMARINE_SERVICE_USERNAME`,
`COPERNICUSMARINE_SERVICE_PASSWORD`), NASA Earthdata in `~/.netrc`. Neither is in the
repository.

## Layout

| Path | What |
|---|---|
| `oceanembed/config.py` | Every number that fixes the shape of the system |
| `oceanembed/fetch.py`, `grid.py`, `arco.py`, `cf.py` | Ingest and regridding, with provenance |
| `oceanembed/argo.py` | Argo casts: adjusted first, QC kept, potential temperature |
| `oceanembed/model.py`, `train.py`, `data.py` | Encoders, decoder, training |
| `oceanembed/baselines.py` | Climatology and linear baselines |
| `oceanembed/predict.py` | Daily NetCDF output and the embedding artefact |
| `oceanembed/evaluate.py`, `embed.py` | The harness and the embedding inspection |
| `oceanembed/api.py`, `viewer/` | The PoC: FastAPI and a CesiumJS viewer |
| `configs/` | One file per model run |
| `docs/` | Problem statement, requirements, limitations, sources, results, ledgers |
