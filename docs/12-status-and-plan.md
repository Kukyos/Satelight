# Status and plan — 2026-09-28

Where the project stands, what was interrupted, how to resume, and what is left before
every requirement in `02-requirements.md` is `done`. No accuracy figures appear here:
they come only from the harness, in `13-eval-results.md`.

## Done

| Piece | Where | Proof |
|---|---|---|
| Ingest of all eight inputs and the target, 2010-02-04 → 2024-12-15, on the 240 × 100 grid | `oceanembed/fetch.py`, `grid.py`, `data/cube/` | `tests/test_cube.py` (grid, daily axis, 15 depths, shelf mask, provenance on every file); `tests/test_reproduce.py --live` (a re-fetch is bit-identical) |
| Extended window 1993 → 2009, every source (D-07) | `data/cube/`, `python -m oceanembed.fetch <source> extended` | Same tests |
| Mixed-layer depth 2021–2024, the probe label (never an input) | `data/cube/mld/` | — |
| Argo casts for the test block | `data/cache/argo_erddap/` | QC kept, rejected levels counted |
| Baselines: climatology and per-cell ridge | `oceanembed/baselines.py`, `runs/climatology`, `runs/linear` | `baselines.demo()` |
| Encoders (U-Net, CNN + transformer hybrid), decoder, training | `oceanembed/model.py`, `train.py`, `configs/` | `tests/test_train_repro.py --live`: the same config and seed give a bit-identical run for both encoders |
| Training recipe chosen on the validation block | `configs/dev/` | Reported by the harness under "How the training recipe was chosen" |
| Output writer (daily NetCDF) and embedding artefact | `oceanembed/predict.py` | — |
| Harness: Argo and INCOIS gridded Argo, per depth and basin, beside climatology and GLORYS; validation-only model selection; embedding inspection with controls | `oceanembed/evaluate.py`, `embed.py` | `evaluate.demo()`, `embed.demo()` |
| PoC viewer and API | `viewer/`, `oceanembed/api.py`, `start.bat` / `start.sh` | Checked end to end on a throwaway model (since deleted) |

What the development runs showed, in words (their figures are in the harness report):

- **Overfitting.** The first models overfit within a few epochs. Eleven training years
  are only about 4,000 strongly correlated days.
- **Warming trend.** The validation years are warmer in the thermocline than the
  training years. GLORYS has no step at its mid-2021 continuation: the warming is
  gradual and sea level rises with it, so the satellite inputs carry the signal.
- **Recipe.** Anomaly target, six epochs, weight decay 1e-2. Crops, dropout, input noise
  and 30 days of input history did not help on the validation block.

## Interrupted at shutdown

`runs/unet` is complete (six epochs; identical, as expected, to its development twin
with the same config and seed). The `hybrid` run had just started and is cut off; it,
`unet-history` and `unet-no-currents-winds` are still to train. Nothing was scored. Everything written so far
is complete: every fetch writes to a `.part` name and renames at the end.

## Resume — in this order

```
# 1. The three remaining runs, one after another on the GPU (≈ 45 min; the hybrid is the slow one)
python -m oceanembed.train configs/hybrid.toml
python -m oceanembed.train configs/unet-history.toml
python -m oceanembed.train configs/unet-no-currents-winds.toml

# 2. The headline model is named from validation loss alone, before any test score
python -c "from oceanembed.evaluate import selection; print(selection()['headline'])"

# 3. Its daily output and embeddings for the test block
python -m oceanembed.predict <headline> 2023-01-01 2024-12-15

# 4. The extended-window comparison (data already fetched)
python -m oceanembed.train configs/unet-extended.toml

# 5. The harness: writes docs/13-eval-results.md, data/eval-latest.json, data/eval-profiles.json
python -m oceanembed.evaluate

# 6. The PoC
start.bat          (or ./start.sh)
```

Run long jobs detached, so they survive the terminal closing. On Windows:

```
Start-Process .venv\Scripts\python.exe -ArgumentList "-u -m oceanembed.train configs/unet.toml" `
  -RedirectStandardOutput data\logs\train-unet.log -RedirectStandardError data\logs\train-unet.err
```

Keep the machine plugged in and awake while they run.

## Left before every requirement is `done`

1. **Steps 1–5 above.** They produce the first real `13-eval-results.md`. After that,
   S5, S6a, S7, E3, E4 and E5 can move to `done` with their proofs.
2. **S4 / E2: read the embedding inspection.** The season clustering has to beat the
   day-of-year control, and the mixed-layer-depth probe has to beat the raw-feature
   probe. If either fails, the report says so and the requirement stays `wip` with the
   reason.
3. **E6: review the viewer on the real model** over both basins. The error view and the
   Argo casts come from the harness output.
4. **Status column.** Update `02-requirements.md`, and 00-start-here's plan of work, in
   the same pass as each item above.
5. **Open ledger items.**
   - D-03: ask INCOIS for the LAS endpoint.
   - D-06: measure the salinity reprocessed/real-time join before extending the output
     past 2024-12-15.
6. **Move the project to `G:\Projects\SIH26P4`** once nothing is running. Keep
   `data/cache`. Rebuild `.venv` at the new path; the torch wheel is in `.wheels/`.
7. **Then the deck and the film.** Every figure in them traces to `13-eval-results.md`.

## Disk

About 78 GB, mostly regenerable:

| Folder | What | Needed for |
|---|---|---|
| `data/cache/arco` | Raw Copernicus chunks | Re-running a fetch only |
| `data/cache/glorys025` | GLORYS levels on the grid, per time block | Rebuilding a GLORYS year only |
| `data/cube` | The training cube | Everything |
| `.venv` | Python environment | Everything |
| `.wheels` | The CUDA torch wheel | Rebuilding `.venv` |
