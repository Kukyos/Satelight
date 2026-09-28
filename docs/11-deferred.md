# Deferred — knowingly incomplete, with what it blocks

The live status document. Appended to in the same pass as the shortcut, never cleaned up
at the end. Resolved items are struck through with the date, not deleted.

| ID | What | Blocks | What it would take |
|---|---|---|---|
| ~~D-01~~ | ~~**No NASA Earthdata login.**~~ **Resolved 2026-09-27**: credentials in `~/.netrc`; `earthaccess` login and one-granule fetches of OSCAR and CCMP succeed. | — | — |
| ~~D-02~~ | ~~**PyTorch on Python 3.14 + CUDA on Windows unverified.**~~ **Resolved 2026-09-27**: the venv is pinned to Python 3.13; torch 2.9.1+cu128 sees the RTX 4060. The campus network intercepts `download-r2.pytorch.org` with a foreign certificate, so the wheel is fetched from `download.pytorch.org` with TLS verification on and checked against the index's SHA-256 before install (`.wheels/`, gitignored). | — | — |
| D-03 | **INCOIS LAS URL unknown.** The problem statement names the source without a link, and our guess `incois.gov.in/las/` returns 404. ERDDAP gridded Argo is substituted. | Claiming we used INCOIS's cited product. | Ask INCOIS, or find the LAS endpoint. Compare its grid to ERDDAP's. |
| ~~D-04~~ | ~~**ARCO access verified only for GLORYS.**~~ **Resolved 2026-09-27**: OSTIA, SSS, DUACS and the GLORYS static store all open through ARCO; their time-series (`geoChunked`) stores are what the ingest reads. | — | — |
| ~~D-05~~ | ~~**OSCAR and CCMP grid alignment unchecked.**~~ **Resolved 2026-09-27**: CCMP centres are at x.125 (the common lattice, pass-through). OSCAR centres are on the quarter degree, half a cell off; regridded by the half-cell shift in `grid.py`, recorded as an interpolation. | — | — |
| D-06 | **SSS reprocessed → NRT join at 2024** unchecked for a step change. | Extending the output past 2024-12-15. The training window stops there so the join is not needed for any score. | Compare the two over their 2024 overlap. Report the bias and decide. |
| D-07 | **Extended window 1993 → 2010.** *2026-09-28: data fetched for 1993–2009, every source. Left: train `configs/unet-extended.toml` (role `comparison`) after the main runs; the harness labels it.* The main model uses the satellite-salinity era only (from 2010-02-04). A second run over 1993 onward, where the "satellite" salinity is not from SMOS/SMAP, is planned as a labelled comparison. | The comparison "does more (partly non-satellite) history help?". | Three more GLORYS time blocks (~30 GB through the chunk cache) and the input years; then one config with an earlier train block, scored by the same harness. |
| D-08 | **Fetch speed on the campus link.** ~8 MB/s total, and connections are dropped now and then; every source-year is retried whole with backoff. GLORYS is the long pole (≈640 MB per level per 5.7-year block). | Time to a full cube, not correctness. | Nothing structural: the fetch is resumable at level-block granularity. |
