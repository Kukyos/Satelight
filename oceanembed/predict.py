"""Reconstruct: satellite surface fields in, daily 3D temperature out.

    python -m oceanembed.predict unet 2023-01-01 2024-12-15 [--embedding-only]

writes, per day,

    data/output/daily/OceanEmbed_thetao_YYYYMMDD.nc
        thetao (depth: 15, lat: 100, lon: 240), degrees_C, potential temperature

and, per year, the embedding artefact (docs/03-limitations.md L10)

    data/output/embedding/<run>_YYYY.nc
        cell  (time, feature: 32, lat, lon)   float32, the per-cell embedding
        daily (time, feature: 64)             the per-day embedding

Every file carries the same provenance the training cube did, plus the run's config.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import torch
import xarray as xr

from . import config, data
from .train import load_model

EMB_DIR = config.OUTPUT / "embedding"
DAILY_DIR = config.OUTPUT / "daily"


def predict_span(run: str, a: date, b: date, with_embedding: bool = False,
                 batch: int = 8):
    """(T, 15, H, W) degrees C with the shelf masked, days, and optionally embeddings."""
    model, cfg, stats = load_model(run)
    x, _, t = data.load_raw("span", cfg["inputs"], with_target=False, span=(a, b),
                            lags=cfg["lags"])
    sea = data.sea_mask()
    xa = data.assemble(x, t, stats, sea)
    del x
    preds, cells, days = [], [], []
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
        for i in range(0, len(xa), batch):
            xb = torch.from_numpy(xa[i:i + batch]).cuda().float()
            e, g = model.embed(xb)
            preds.append(model.decoder(e).float().cpu().numpy())
            if with_embedding:
                cells.append(e.float().cpu().numpy())
                days.append(g.float().cpu().numpy())
    from .train import target_offset
    y = (data.denormalise_target(np.concatenate(preds), stats) + target_offset(cfg, t)
         ).astype(np.float32)
    y[:, ~level_mask()] = np.nan
    emb = (np.concatenate(cells), np.concatenate(days)) if with_embedding else None
    return y, t, emb


def level_mask() -> np.ndarray:
    """(15, H, W): where each target depth exists, from the GLORYS cube's own NaNs (the
    shelf mask is static, so any one day of any year gives it)."""
    path = config.CUBE / "levels_mask.npy"
    if not path.exists():
        f = sorted((config.CUBE / "glorys").glob("*.nc"))[0]
        with xr.open_dataset(f) as ds:
            np.save(path, np.isfinite(ds["thetao"].isel(time=0).values))
    return np.load(path)


def _provenance(run: str, cfg: dict) -> dict:
    return {
        "model_run": run, "model_config": cfg,
        "inputs": {v: data.SOURCE_OF[v] for v in cfg["inputs"]},
        "target_trained_on": "GLORYS12 cmems_mod_glo_phy_my_0.083deg_P1D-m thetao",
        "zero_metre_rule": config.ZERO_METRE_RULE,
        "vertical": config.VERTICAL_METHOD,
        "mask": "cells shallower than a level are NaN, never extrapolated",
        "note": "inputs are satellite surface observations and static fields only",
    }


def write_daily(run: str, y: np.ndarray, t: np.ndarray, cfg: dict) -> None:
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    prov = json.dumps(_provenance(run, cfg))
    for i, day in enumerate(t):
        ds = xr.Dataset(
            {"thetao": (("depth", "lat", "lon"), y[i], {
                "standard_name": "sea_water_potential_temperature", "units": "degrees_C",
                "long_name": "reconstructed potential temperature"})},
            coords={
                "time": np.datetime64(day, "ns"),
                "depth": ("depth", config.DEPTHS, {"units": "m", "positive": "down",
                                                   "standard_name": "depth"}),
                "lat": ("lat", config.LAT, {"units": "degrees_north",
                                            "standard_name": "latitude"}),
                "lon": ("lon", config.LON, {"units": "degrees_east",
                                            "standard_name": "longitude"})},
            attrs={"title": "OceanEmbed subsurface temperature reconstruction",
                   "Conventions": "CF-1.8", "institution": "SIH 2026 PS 26066",
                   "resolution": "0.25 degree, daily, 15 standard depths",
                   "provenance": prov})
        ds.to_netcdf(DAILY_DIR / f"OceanEmbed_thetao_{str(day).replace('-', '')}.nc",
                     encoding={"thetao": {"zlib": True, "complevel": 4}})


def write_manifest(run: str, a: date, b: date, t: np.ndarray) -> None:
    """The span asked for, the days written, and each day skipped with its reason, so a
    gap in the daily files is recorded where the output lives."""
    want = np.arange(np.datetime64(a), np.datetime64(b) + np.timedelta64(1, "D"))
    skipped = sorted(set(want.astype(str)) - set(t.astype("datetime64[D]").astype(str)))
    (DAILY_DIR / "manifest.json").write_text(json.dumps({
        "model_run": run, "span": [str(a), str(b)], "days_written": int(len(t)),
        "days_skipped": {d: "an input has no value over the box that day; see the input "
                            "cube's provenance (missing_days / empty_days)" for d in skipped},
    }, indent=1))


def write_embedding(run: str, emb, t: np.ndarray) -> None:
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    cell, daily = emb
    years = t.astype("datetime64[Y]").astype(int) + 1970
    for y in np.unique(years):
        k = years == y
        xr.Dataset({"cell": (("time", "feature", "lat", "lon"), cell[k]),
                    "daily": (("time", "dfeature"), daily[k])},
                   coords={"time": t[k].astype("datetime64[ns]"), "lat": config.LAT,
                           "lon": config.LON},
                   attrs={"model_run": run}
                   ).to_netcdf(EMB_DIR / f"{run}_{y}.nc",
                               encoding={"cell": {"zlib": True, "complevel": 1}})


if __name__ == "__main__":
    # `--embedding-only`: a run that is not the headline writes its embedding artefact
    # without overwriting the headline's daily files.
    run, a, b = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
    _, cfg, _ = load_model(run)
    y, t, emb = predict_span(run, a, b, with_embedding=True)
    if "--embedding-only" not in sys.argv:
        write_daily(run, y, t, cfg)
        write_manifest(run, a, b, t)
    write_embedding(run, emb, t)
    print(f"wrote the embedding for {run}" + ("" if "--embedding-only" in sys.argv
                                             else f" and {len(t)} daily files"))
