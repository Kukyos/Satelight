# Deferred — knowingly incomplete, with what it blocks

The live status document. Appended to in the same pass as the shortcut, never cleaned up
at the end. Resolved items are struck through with the date, not deleted.

| ID | What | Blocks | What it would take |
|---|---|---|---|
| D-01 | **No NASA Earthdata login.** No `.netrc` on this machine. OSCAR, CCMP and ASCAT all need one. | Inputs S3d (currents) and S3e (winds). The model can start on SST + SSS + SSH, but it is not the problem statement's model until these are in. | Register at urs.earthdata.nasa.gov, put the credentials in `.netrc` (never in the repo), and fetch one day of each to verify. |
| D-02 | **PyTorch on Python 3.14 + CUDA on Windows unverified.** | Training. | Try the CUDA wheel in a fresh venv. If it fails, pin this project's venv to Python 3.13, recorded here. |
| D-03 | **INCOIS LAS URL unknown.** The problem statement names the source without a link, and our guess `incois.gov.in/las/` returns 404. ERDDAP gridded Argo is substituted. | Claiming we used INCOIS's cited product. | Ask INCOIS, or find the LAS endpoint. Compare its grid to ERDDAP's. |
| D-04 | **ARCO access verified only for GLORYS.** OSTIA, SSS and DUACS are assumed to open the same way. | Fetch speed; a fallback is the toolbox's `subset`. | Open each store once and record the time in `05-data-sources.md`. |
| D-05 | **OSCAR and CCMP grid alignment unchecked** against the DUACS x.125 lattice. | Whether they pass through natively or need regridding. | Read the coordinate arrays from one file of each. |
| D-06 | **SSS reprocessed → NRT join at 2024** unchecked for a step change. | Using 2025 as test data. | Compare the two over their 2024 overlap. Report the bias and decide. |
