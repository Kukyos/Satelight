# Unsourced — values we could not source, and where the real one comes from

Anything here is structurally present and visibly unsourced. Never quoted as fact.
Appended to in the same pass as the shortcut, never as a cleanup at the end.

| Value | Status | Where the real one comes from |
|---|---|---|
| ~~GLORYS top level ≈ 0.49 m, 50 levels~~ | **Measured 2026-09-27**: 50 levels, top 0.494 m (`05-data-sources.md`, "Measured on fetch"). | — |
| Content of the SSS product before about 2010 | Unknown. SMOS launched in 2009 and SMAP in 2015, so earlier salinity is not from either. | The product user manual (QUID/PUM) for `MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013`. |
| Whether INCOIS LAS "Gridded ARGO" is the same analysis as ERDDAP `incois_argo_10d_VAM` | Assumed to be the same family; substituted and labelled as a substitution. | INCOIS directly, or a LAS URL. |
| Cube sizes in `03-limitations.md` L8 | Arithmetic estimates, not measurements. | The first full-year fetch. |
| Whether GLORYS after mid-2021 is the same run as before it | The store holds real values through 2026-06-23 under one dataset ID; historically the multi-year run was extended by an interim run. The test block (2023–2024) lies in that later part. | The GLORYS12 product user manual / quality document for `GLOBAL_MULTIYEAR_PHY_001_030`. |
| cmocean `thermal`, `haline`, `balance` colour stops in the viewer | Approximated from published anchor points (carried from PS 26067), not the full tables. | The cmocean package's colour tables. |
| The 0.2 × depth (min 25 m) gap limit for interpolating an Argo cast onto the 15 depths | Our choice, set to follow typical core-Argo vertical spacing; not from a standard. | An Argo or INCOIS validation guideline, if one prescribes it. |
| The 50 % water share needed for a 0.25° cell to count as sea at a level | Our choice. | Sensitivity of the scores to it, measured by the harness. |
| The cyclone boxes in `config.CYCLONES` (Mocha 87–94°E 10–19°N, Biparjoy 63–70°E 12–22°N) and the ±3-day margin | Our choice, drawn to enclose the tracks the IMD bulletins describe; the storm dates themselves are IMD's. | IMD best-track positions, and a box derived from them. |
| Reference density 1025 kg/m³ in the heat potential (TCHP) | Our stated choice (carried from PS 26067 N8); operational products differ. cp is the TEOS-10 cp0. | The convention INCOIS uses for its own TCHP product. |
| Heatwave baseline: 11 training years (2010-02-04 → 2020-12-31) of GLORYS, not Hobday et al.'s 30 | Our choice, forced by the record. A shorter baseline gives noisier percentiles; being fixed, it also counts the warming since as more exceedances, as Hobday recommends. | A 30-year subsurface baseline (GLORYS from 1993, in the extended cube). |
| Heatwave layer 50–150 m, and a cell counting as sea for the globe's SST when 13 of its 25 native cells are | Our choices: the layer spans the top of the thermocline in both basins; half the block for the globe mirrors the box's sea share. | Sensitivity of the heatwave scores to the layer, measured by the harness. |
| The Turbo colour stops (11 anchors) | Approximated from Mikhailov's published polynomial, not the full 256-entry table. | Google's `turbo_colormap` table. |
| 26 °C at the middle of the temperature colour bar | A display choice. 26 °C itself is sourced (the heat potential threshold, Leipper and Volgenau 1972). | — |
| The Dive's darkening | Illustrative, not a light field. The zones it names are NOAA National Ocean Service's (rarely any significant light below 200 m; some detectable to 1,000 m). | Satellite Kd490 for the day, if the darkening is ever to be measured. |
| "A shallow thermocline brings tuna within reach of surface gear" | Sourced as stated in Marsac, IOTC-2008-WPTT-27 (purse-seine catch rates in the western Indian Ocean fell when the thermocline deepened; schools concentrated where it was shallow). Not a rule for any other gear or species, and not a catch forecast. | INCOIS's own tuna advisory method, if published. |
