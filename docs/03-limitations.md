# The limitations map

Written before any code, because each item fixes a decision that everything downstream
depends on. Each limit ends with the **constraint** it forces. When real data proves one
wrong, it is corrected here with the date and marked, never silently rewritten.

---

## L1 · Independence — nothing recommended here is independent of Argo

The problem statement asks for validation against *independent* observations. But:

- **GLORYS12**, the training target, assimilates Argo temperature profiles.
- **OSTIA**, the SST input, assimilates in-situ SST.
- **The SSS product** is multi-observation and may blend in-situ salinity (unverified,
  `05-data-sources.md` §2.2).
- **INCOIS gridded Argo** is built *from* Argo.

A model trained to reproduce GLORYS and then scored against Argo is partly scored
against data its target already contains.

> **Constraint:** the test set is a **time-blocked hold-out**: the last contiguous block
> of the window is never seen in training or model selection. Every score is reported
> beside two references on the same profiles: **climatology** (the floor) and **GLORYS
> itself** (the ceiling). A model that "beats GLORYS against Argo" is a red flag to
> investigate, not a headline.

## L2 · Splits — random days leak

Neighbouring days are nearly identical, and a mesoscale eddy lives for weeks. A random
day-level split puts the day before and the day after a test day into training.

> **Constraint:** train / validation / test split by **contiguous time blocks**, with a
> gap of at least a month between blocks. Never a random split, and no random spatial
> tiles.

## L3 · The window — set by the shortest source

From the catalogue ranges (`05-data-sources.md` §6), the intersection is
1993-01-01 → 2026-01-16 with the salinity records stitched. But salinity before
SMOS (about 2010) cannot be satellite salinity, whatever the product contains.

> **Constraint:** the training window is the **measured** intersection of what was
> actually fetched, recorded in `13-eval-results.md`. If pre-2010 salinity is not
> satellite data, either the window starts around 2010 or the deck says so. The model's
> claim is "from surface satellite observations only", and the inputs have to honour it.

## L4 · The grid — adopt one source's lattice, regrid the rest onto it

The problem statement fixes 0.25° daily over 45–105°E × 5–30°N. DUACS is already 0.25°
with cell centres at x.125. OSTIA (0.05°) and SSS (0.125°) divide into it exactly.
GLORYS (1/12°) divides into it 3 × 3.

> **Corrected 2026-09-27, on the data.** GLORYS divides into the grid three-to-one in
> *size* but not in *alignment*: its centres sit on multiples of 1/12°, so the
> 0.25° cell edges run through the middle of GLORYS cells. The exact conservative mean
> is a 4-wide stencil at stride 3 with weights ½, 1, 1, ½ per axis (`grid.py`). OSCAR's
> centres are on the quarter degree, half a cell off the lattice; it is shifted by the
> mean of the four surrounding cells, which is an interpolation, and is labelled so.

Domain: **240 lon × 100 lat = 24,000 cells** per day, before the land mask.

> **Constraint:** the common grid is the DUACS lattice. Coarser-from-finer is always a
> **block mean**, never interpolation, so no value is invented. Any source that does not
> align exactly is regridded with its method recorded in
> the provenance. Nothing is regridded finer than it is. Checked 2026-09-28 on real data
> for every input (`tests/test_sources.py --live`): CCMP sits on the lattice and passes
> through; OSCAR is the half-cell shift described above.

## L5 · Depth — fifteen target levels, and the two ends are awkward

The target levels are `0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200, 300, 500, 700, 1000`
m. GLORYS has 50 native levels, so 15 is a subset of the information and invents none.

But:

- **GLORYS has no 0 m level.** Its top level is about 0.49 m (from PS 26067,
  re-verify). "0 m" needs a stated rule: take the top level as 0 m, or use the SST
  input. Using SST would put an input straight into the output.
- **Levels between GLORYS levels** need vertical interpolation. Linear in depth is the
  default, and whatever is used is recorded.
- **Shelf cells shallower than a level** (the Gulf of Kutch, the Palk Strait, the
  Sundarbans shelf, the Persian Gulf mouth) have no water at 200 m.

> **Constraint:** the 0 m rule and the vertical interpolation method are written into
> the output's attributes. Cells shallower than a level are **masked from the GLORYS
> static `deptho`**, never extrapolated, and the loss ignores them. The output never has
> more than these 15 levels.

## L6 · Validation resolution — compare at the coarser grid, never upsample

Individual Argo profiles are points at irregular depths. INCOIS gridded Argo is 1°,
10-day, 24 levels. Our output is 0.25°, daily, 15 levels.

> **Constraint:** point profiles are compared at the model cell and day containing them,
> interpolated onto the 15 levels. Profiles are never extrapolated beyond their deepest
> good level. Gridded Argo is compared at **its** 1° / 10-day resolution, averaging our
> output down, never upsampling the reference. Every Argo value keeps its QC flag and
> data mode, and profiles failing QC are counted as rejected, not silently dropped.

## L7 · The files are not as clean as they claim

Measured in PS 26067: INCOIS labels temperature units as `"degs"` and gives no `positive`
on the depth axis. Argo reports pressure, not depth. We have not yet opened the other
sources.

> **Constraint:** every ingest step normalises through one CF layer that **records every
> normalisation it made**. That record travels with the data into the training cube and
> the output file.

## L8 · Compute — measured on this machine

RTX 4060 Laptop GPU (8 GB), i7-13700HX, 32 GB RAM, 160 GB free disk (2026-09-26).

Rough size of the full cube, 1993–2025 (about 12,000 days × 24,000 cells), as float32:
7 input channels ≈ 8 GB, 15 target levels ≈ 17 GB. That fits on disk, and fits in RAM
per year, not whole. Estimated, not measured; replace with measured sizes.

> **Constraint:** the training set is stored on disk as per-year chunked arrays and
> streamed, not loaded whole. Models are sized to train in hours on 8 GB, not days. The
> fetch is the slow part: roughly 12,000 days × 6 sources. It runs once, resumable, in
> the background.

## L9 · "Only surface satellite observations" — what goes in, and what doesn't

The objective is to estimate 3D temperature "using only surface satellite observations".
GLORYS also offers `mlotst` (mixed-layer depth) and its own surface currents, and both
would improve a model a lot. But neither is a satellite observation.

> **Constraint:** model inputs are the five listed variables (plus static fields: lat,
> lon, bathymetry, day-of-year). Nothing from GLORYS goes in as an input. If an
> experiment breaks this, it is labelled as an ablation, never shown as the model.

> **Decision, 2026-09-28:** the bathymetry channel and the sea mask are taken from the
> GLORYS static file (`deptho`, regridded with the same stencil). They are fixed
> properties of the sea floor, identical on every day, and carry nothing about the
> ocean's state; using the target's own sea floor also keeps the input mask and the
> output mask identical. An independent bathymetry (GEBCO, ETOPO) would serve equally
> and is the substitute if this is challenged. Nothing time-varying from GLORYS goes in.

> **Decision, 2026-09-28: the anomaly target.** The models learn the departure from the
> train-block day-of-year climatology of GLORYS (`runs/climatology`), and that
> climatology is added back on output. It is fitted on training targets only, it is the
> same on every year, and it depends only on the cell and the day of year — the same
> information a network could memorise from its latitude, longitude and day-of-year
> inputs. It is therefore treated as a fixed part of the model (a learned prior), not as
> an input. What changes from day to day in the output comes from the satellite fields
> alone. Chosen on the validation block (`13-eval-results.md`, "How the training recipe
> was chosen").

## L10 · The embedding has to be a thing, not a claim

The problem statement's title is *embedding-based*. A network with a hidden layer
technically has an embedding, but judges will ask what it captures.

> **Constraint:** the embedding is saved as its own artefact per cell per day. It gets
> an inspection: projection, nearest-neighbour days, clustering by season or eddy
> polarity, and a linear probe for something it was never trained on (mixed-layer depth
> from GLORYS). Anything claimed about what the latent space encodes is measured by the
> harness.
