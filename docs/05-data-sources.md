# Data sources — probed, not assumed

First probe **2026-09-26**, from this machine. Each finding is marked with how far it was
checked:

- **resolved**: the link returns HTTP 200 and lands on the product page
- **catalogue**: dataset IDs, variables, grid and time range read from the provider's
  catalogue (`copernicusmarine.describe` for Copernicus, NASA CMR for PO.DAAC)
- **fetched**: real data downloaded and opened. Reached 2026-09-27 for every source
  in §1–§5 (see "Measured on fetch" at the end).

Nothing here is quoted from documentation unless it says so.

---

## The headline

1. **Every link in the problem statement resolves.** Unlike PS 26067, where both FTP
   links were dead, all seven dataset URLs return 200.
2. **Two of the five inputs need a NASA Earthdata login** (OSCAR currents, CCMP winds).
   None was found on this machine. See `11-deferred.md` D-01.
3. **The recommended products do not all cover the same years.** Their common window is
   set by the salinity and SSH records (§6).
4. **The "Gridded ARGO" source has no URL.** The text names "INCOIS Live Access Server
   (LAS)" without a link. INCOIS's public ERDDAP serves gridded Argo analyses, and we
   have used it before (§5). That is a substitution, and is recorded as one.

---

## 1 · Target: GLORYS12 reanalysis — catalogue

DOI `10.48670/moi-00021` → `GLOBAL_MULTIYEAR_PHY_001_030`.

| Dataset | Use |
|---|---|
| `cmems_mod_glo_phy_my_0.083deg_P1D-m` | **Training target.** Daily. `thetao` (temperature), also `so`, `uo`, `vo`, `mlotst`, `bottomT` |
| `cmems_mod_glo_phy_my_0.083deg_static` | `deptho`, `mask`: masks cells shallower than a target level |
| `cmems_mod_glo_phy_my_0.083deg-climatology_P1M-m` | Monthly climatology: a candidate floor baseline |

Grid 1/12° (lat −80 → 90, lon −180 → 179.917). Daily record **1993-01-01 → 2026-06-23**.

Known from the PS 26067 work (not re-probed here): 50 native depth levels, with the top
level at about 0.49 m, **not 0 m**. Opening the ARCO Zarr store directly took 3.6 s once
per process; one day of a 15° × 15° box at all levels took 3–7 s cold.

GLORYS **assimilates Argo**. That limits what "independent" can mean (`03-limitations.md` L1).

## 2 · Inputs from Copernicus Marine — catalogue

Our Copernicus account from PS 26067 works for these. Each needs regridding to the
common 0.25° grid unless noted.

### 2.1 SST: OSTIA reprocessed — `SST_GLO_SST_L4_REP_OBSERVATIONS_010_011`

DOI `10.48670/moi-00168`. Dataset `METOFFICE-GLO-SST-L4-REP-OBS-SST`.
Variables `analysed_sst`, `analysis_error`, `mask`, `sea_ice_fraction`. 0.05° daily,
**1981-10-01 → 2026-03-31**. Regrid: 5 × 5 block mean.

### 2.2 SSS: multi-observation surface salinity — `MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013`

DOI `10.48670/moi-00051`. The problem statement calls this "SMAP, SMOS". **It is a
multi-observation L4 product**, which may blend in-situ data with satellite data. Check
the product manual before calling it satellite-only.

| Dataset | Range |
|---|---|
| `cmems_obs-mob_glo_phy-sss_my_multi_P1D` (reprocessed) | **1993-01-01 → 2024-12-15** |
| `cmems_obs-mob_glo_phy-sss_nrt_multi_P1D` (near-real-time) | **2024-01-01 → 2026-09-20** |

Variables `sos` (salinity), `sos_error`, `dos` (density), `dos_error`. 0.125° daily.
Regrid: 2 × 2 block mean.

- The reprocessed and NRT records overlap for 2024. Using both means stitching them, and
  the join has to be checked for a step.
- SMOS launched in 2009 and SMAP in 2015, so salinity before about 2010 cannot come from
  either. What the product contains there is **unverified**.

### 2.3 SSH / SLA: DUACS — `SEALEVEL_GLO_PHY_CLIMATE_L4_MY_008_057`

DOI `10.48670/moi-00145`. Dataset `c3s_obs-sl_glo_phy-ssh_my_twosat-l4-duacs-0.25deg_P1D`.

This is the **C3S "twosat" climate product** (a stable two-satellite constellation), not
the all-satellite DUACS product. Variables `sla`, `adt`, `ugos`/`vgos` (geostrophic
currents), `ugosa`/`vgosa`, and error fields. 0.25° daily, **1993-01-01 → 2026-01-16**,
cell centres at x.125. **Native resolution: no regridding.** We adopt this grid as the
common grid.

## 3 · Inputs from NASA PO.DAAC — catalogue, blocked on login

Queried through NASA CMR (`cmr.earthdata.nasa.gov/search/collections.json`). Downloading
requires an Earthdata account.

| Short name | What it is | Range (CMR) | Note |
|---|---|---|---|
| `OSCAR_L4_OC_FINAL_V2.0` | Surface currents, 0.25° daily L4 | 1993-01-01 → 2026-01-17 | Native 0.25°. Grid alignment to DUACS unchecked |
| `CCMP_WINDS_10M6HR_L4_V3.1` | 10 m winds, 0.25° **6-hourly** L4 | 1993-01-01 → open | Daily mean of four synoptic times. Coverage ±80° lat |
| `ASCATC-L2-Coastal` | MetOp-C ASCAT winds, **L2 swath** | 2019-10-22 → open | **Not a gridded product.** Along-track swaths would need gridding and gap-filling, and the record starts in 2019. CCMP is the wind input; ASCAT is a candidate for independent wind validation |

## 4 · In-situ profiles (validation) — not yet probed for this project

Carried over from PS 26067, where it was fetched and used:

- **Argo profiles**, Ifremer GDAC over HTTPS (`data-argo.ifremer.fr`) and Ifremer's Argo
  ERDDAP (`ArgoFloats`, `ArgoFloats-synthetic-BGC`). Per-level QC flags, `DATA_MODE`
  (A/R/D), pressure rather than depth (TEOS-10 conversion needs latitude).
- These are the **independent observations** the problem statement asks for, with the
  caveat in `03-limitations.md` L1.

## 5 · "Gridded ARGO", INCOIS LAS — substitution

The problem statement names "INCOIS Live Access Server (LAS) – Gridded ARGO" with no URL.
`https://incois.gov.in/las/` returned **404** on 2026-09-26. That URL was our guess; it is
not from the problem statement.

INCOIS's public ERDDAP (`https://erddap.incois.gov.in/erddap/`) serves INCOIS's gridded
Argo analyses. These were fetched and used in PS 26067 (measured there on 2026-09-22):

| Dataset ID | Method | Grid |
|---|---|---|
| `incois_argo_10d_VAM` | Variational analysis; `TEMP`, `SAL`, per-cell error `TERR`/`SERR` | 1°, ~10-day, 24 levels 5–2000 m, 29.5°S–29.5°N, 30.5–119.5°E, 2004 → 2026-07-30 |
| `incois_argo_10day_McCreary` | Kessler–McCreary objective analysis | same family |
| `*_mnt_*` | Monthly equivalents | |

Its latitude limit (29.5°N cell centre) stops just short of the 30°N box edge. It is used
at its own 1° / 10-day resolution and never upsampled (`03-limitations.md` L5). The file
also misstates its own units and axes: TEMP is labelled `"degs"`, and the depth axis has
no `positive` attribute.

**Open question for INCOIS:** is the LAS product the same analysis as the ERDDAP one?
Logged in `11-deferred.md` D-03.

## 6 · The common training window — from catalogue ranges

| Source | Start | End |
|---|---|---|
| GLORYS12 daily | 1993-01-01 | 2026-06-23 |
| OSTIA reprocessed | 1981-10-01 | 2026-03-31 |
| SSS reprocessed / NRT | 1993-01-01 | 2024-12-15 / 2026-09-20 |
| DUACS twosat | 1993-01-01 | 2026-01-16 |
| OSCAR final | 1993-01-01 | 2026-01-17 |
| CCMP v3.1 | 1993-01-01 | open |

The intersection is **1993-01-01 → 2026-01-16** if the SSS records are stitched, and
**→ 2024-12-15** if not. The real start depends on §2.2: if salinity before about 2010 is
not satellite data, then either the window starts around 2010 or that fact is stated. To
be decided on data, not here.

## 7 · Tooling

- `copernicusmarine` toolbox (2.4.1 in the PS 26067 environment) for describe and
  subset; direct ARCO Zarr opening for speed. Opening all these datasets through ARCO is
  **unverified**; so far only GLORYS has been opened that way.
- `earthaccess` or plain HTTPS with `.netrc` for PO.DAAC, once there is a login.
- TLS verification stays on. If a host serves an incomplete certificate chain, fix it with
  `truststore` or a bundled intermediate, never by disabling verification.

## Measured on fetch — 2026-09-27

Raised to **fetched**. Each line was read from the data, not from documentation.

| Source | What was measured |
|---|---|
| GLORYS12 `thetao` | Read through the ARCO **time-series** store (`geoChunked.zarr`, the toolbox calls it `arco-time-series`). Chunks are 2081 days × 1 level × 16 × 16 cells, packed int16 (scale 0.000732, offset 21, fill −32767). In that store the vertical axis is `elevation`, **deepest first** (index 0 is −5727.9 m), so levels are selected by value. 50 levels, top 0.494 m. Time blocks start 1993-01-01, 1998-09-13, 2004-05-25, **2010-02-04**, 2015-10-17, 2021-06-28; the record runs to 2026-06-23 with real values after mid-2021. One level of one block over the box is ≈ 640 MB compressed. Cell centres on multiples of 1/12°, so they straddle the 0.25° cell edges (see `03-limitations.md` L4). |
| GLORYS static `deptho` | `static-arco` part `bathy`. 7 m to 5,284 m over the box. |
| OSTIA | Centres at x.025 (0.05°), so 5 × 5 blocks nest exactly in the 0.25° cells. `analysed_sst` in kelvin; converted to °C and the conversion recorded. |
| SSS (reprocessed) | Centres at x.0625 (0.125°), so 2 × 2 blocks nest exactly. |
| DUACS twosat | Centres at x.125: the common grid itself. `adt`, `sla` in metres. |
| OSCAR final v2.0 | Global 0.25° daily file, 33 MB, uncompressed chunks of 720 lon × 360 lat. Centres on the quarter degree (0.00, 0.25, …), stored (time, **longitude**, latitude). Fetched as a **server-side OPeNDAP subset** (`opendap.earthdata.nasa.gov`, DAP4), 0.2 MB and ≈ 3.6 s a day. |
| CCMP v3.1 | Global 0.25° file, 33 MB, 4 synoptic times, zlib chunks of the whole globe per time. Centres at x.125. Fetched as an OPeNDAP subset, 0.75 MB and ≈ 6 s a day. The product is "RSS VAM 6-hour analyses using ERA-5 wind reanalysis as background": satellite winds blended over a reanalysis background, stated where the inputs are described. Measured 2026-09-28: 18 days have a granule but no daily wind over the box, one of them (2024-08-31) in the main window. For 2024-08-31 the cause was checked on the source file: the 18 UTC analysis is empty there, and the daily mean needs all four times. These days are listed as `empty_days` in the provenance and dropped by the loader like a missing day. |
| Argo (Ifremer ERDDAP `ArgoFloats`) | Test block 2023-01-01 → 2024-12-15 over the box: 6,345 casts, 8,500 levels failing QC (kept, marked). |
| INCOIS ERDDAP `incois_argo_10d_VAM` | Reachable with TLS verification on (truststore on Windows; bundled GlobalSign intermediate elsewhere). 24 levels 5–2000 m, 1°, ≈ 10-day steps, TEMP labelled `degs`. |

**The campus network.** It intercepts some hosts with its own certificate
(`download-r2.pytorch.org` answered with `*.karunya.edu`), and it resets connections now
and then. TLS verification stays on everywhere; hosts that fail are routed around, never
trusted blindly.

## Display-only sources — 2026-09-30

Shown around the cube, never an input, a target or a score.

| Source | What was measured |
|---|---|
| OSTIA global, reprocessed `METOFFICE-GLO-SST-L4-REP-OBS-SST` | `arco-geo-series` store, chunks 1 day × 1024 × 1024, packed int16, 3600 × 7200 at 0.05°. Records 1981-10-01 → 2026-03-31. One global day reads in ≈ 3.7 s. Block-meaned 5 × 5 to 0.25° (`satelight/globe.py`), sea where ≥ 13 of 25 native cells are sea. |
| OSTIA global, near-real-time `METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2` | Opens the same way; 2026-09-28 was already there on 2026-09-30, **two days' delay**. Used after the reprocessed record ends. |
| NASA Blue Marble shaded relief and bathymetry, GIBS WMTS | Public domain, no key, level 8 (≈ 600 m a pixel). Natural Earth II, bundled with Cesium, shows if GIBS cannot be reached. |

## Re-probing

Every claim marked **catalogue** gets re-checked by the ingest self-checks once real
fetches exist, and the marker is raised to **fetched** with the date.
