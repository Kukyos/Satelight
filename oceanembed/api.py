"""The PoC server: everything the viewer draws comes from here, and only from files the
pipeline and the harness wrote.

    uvicorn oceanembed.api:app --port 8026      (start.bat / start.sh do this)

Arrays travel as base64 little-endian float32 (or uint8 RGB), row-major, south first,
west first; NaN means no water (land, or below the sea floor).
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import xarray as xr
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .fetch import cube_path
from .predict import DAILY_DIR, EMB_DIR

app = FastAPI(title="OceanEmbed")
VIEWER = config.ROOT / "viewer" / "dist"
FIELDS = ["oceanembed", "glorys", "climatology", "error"]
INPUT_UNITS = {"sst": "°C", "sss": "PSU", "adt": "m", "sla": "m", "uc": "m/s", "vc": "m/s",
               "uw": "m/s", "vw": "m/s"}
INPUT_TITLES = {"sst": "Sea surface temperature", "sss": "Sea surface salinity",
                "adt": "Absolute dynamic topography", "sla": "Sea level anomaly",
                "uc": "Current, eastward", "vc": "Current, northward",
                "uw": "Wind, eastward", "vw": "Wind, northward"}
REGIONS = {"Bay of Bengal": config.BASINS["Bay of Bengal"],
           "Arabian Sea": config.BASINS["Arabian Sea"],
           "North Indian Ocean": {"lon": config.LON_EDGES, "lat": config.LAT_EDGES}}


def b64(a: np.ndarray, dtype=np.float32) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype=dtype).tobytes()).decode()


def _day(day: str) -> np.datetime64:
    try:
        return np.datetime64(day, "D")
    except ValueError as e:
        raise HTTPException(400, f"bad day {day!r}") from e


@lru_cache(maxsize=1)
def best_run() -> str:
    runs = [p.parent.name for p in config.RUNS.glob("*/best.pt")]
    files = sorted(DAILY_DIR.glob("*.nc"))
    if files:
        with xr.open_dataset(files[0]) as ds:
            return json.loads(ds.attrs["provenance"])["model_run"]
    return runs[0] if runs else ""


@lru_cache(maxsize=1)
def seafloor() -> np.ndarray:
    with xr.open_dataset(config.CUBE / "static.nc") as s:
        return np.where(s["sea_share"].values >= config.OCEAN_FRACTION_MIN, s["deptho"].values, np.nan)


@lru_cache(maxsize=64)
def field(name: str, day: str) -> np.ndarray:
    """(15, 100, 240) degrees C for one field on one day."""
    d = _day(day)
    if name == "oceanembed":
        path = DAILY_DIR / f"OceanEmbed_thetao_{str(d).replace('-', '')}.nc"
        if not path.exists():
            raise HTTPException(404, f"no reconstruction written for {d}")
        with xr.open_dataset(path) as ds:
            return ds["thetao"].values
    if name == "glorys":
        path = cube_path("glorys", int(str(d)[:4]))
        if not path.exists():
            raise HTTPException(404, f"no GLORYS cube for {str(d)[:4]}")
        with xr.open_dataset(path) as ds:
            return ds["thetao"].sel(time=str(d)).values
    if name == "climatology":
        from .baselines import climatology
        if not (config.RUNS / "climatology" / "clim.npy").exists():
            raise HTTPException(404, "the climatology baseline has not been fitted")
        return climatology(np.array([d]))[0]
    if name == "error":
        return field("oceanembed", day) - field("glorys", day)
    raise HTTPException(400, f"unknown field {name!r}")


def _box(region: str):
    r = REGIONS.get(region)
    if r is None:
        raise HTTPException(400, f"unknown region {region!r}")
    i = (config.LON >= r["lon"][0]) & (config.LON <= r["lon"][1])
    j = (config.LAT >= r["lat"][0]) & (config.LAT <= r["lat"][1])
    return j, i


@app.get("/api/meta")
def meta():
    days = sorted(p.stem.rsplit("_", 1)[-1] for p in DAILY_DIR.glob("*.nc"))
    days = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days]
    return {"run": best_run(), "days": days, "fields": FIELDS,
            "depths": config.DEPTHS.tolist(), "regions": REGIONS,
            "inputs": [{"key": k, "title": INPUT_TITLES[k], "units": INPUT_UNITS[k]}
                       for k in config.INPUTS],
            "splits": {k: [str(a), str(b)] for k, (a, b) in config.SPLITS.items()},
            "zero_metre_rule": config.ZERO_METRE_RULE}


@app.get("/api/cube")
def cube(day: str, name: str = "oceanembed", region: str = "Bay of Bengal"):
    j, i = _box(region)
    v = field(name, day)[:, j][:, :, i]
    finite = v[np.isfinite(v)]
    return {"day": day, "field": name, "region": region,
            "dimensions": [int(i.sum()), int(j.sum()), int(v.shape[0])],
            "lons": config.LON[i].tolist(), "lats": config.LAT[j].tolist(),
            "depths": config.DEPTHS.tolist(),
            "valueRange": [float(finite.min()), float(finite.max())] if finite.size else [0, 1],
            "values": b64(v), "seafloor": b64(seafloor()[j][:, i]),
            "units": "°C" if name != "error" else "°C (OceanEmbed − GLORYS)"}


@app.get("/api/inputs")
def inputs(day: str):
    d = _day(day)
    out = []
    for k in config.INPUTS:
        from .data import SOURCE_OF
        path = cube_path(SOURCE_OF[k], int(str(d)[:4]))
        if not path.exists():
            continue
        with xr.open_dataset(path) as ds:
            a = ds[k].sel(time=str(d)).values
            prov = json.loads(ds.attrs.get("provenance", "{}"))
        f = a[np.isfinite(a)]
        lo, hi = (np.percentile(f, [2, 98]) if f.size else (0, 1))
        out.append({"key": k, "title": INPUT_TITLES[k], "units": INPUT_UNITS[k],
                    "range": [float(lo), float(hi)], "values": b64(a),
                    "source": prov.get("dataset_id") or prov.get("short_name")})
    return {"day": day, "shape": [config.NLAT, config.NLON], "inputs": out}


@lru_cache(maxsize=4)
def _pca(run: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """One PCA basis for the whole test block, so a colour means the same thing on every
    day and a change in colour is a change in the embedding."""
    files = sorted(EMB_DIR.glob(f"{run}_*.nc"))
    if not files:
        raise HTTPException(404, "no embedding written")
    from .data import sea_mask
    sea = sea_mask()
    rows = []
    with xr.open_dataset(files[0]) as ds:
        n = ds.sizes["time"]
        for d in np.linspace(0, n - 1, 24).astype(int):
            rows.append(ds["cell"].isel(time=int(d)).values.astype(np.float32)[:, sea].T)
    v = np.concatenate(rows)
    mu = v.mean(0)
    _, _, vt = np.linalg.svd(v - mu, full_matrices=False)
    pc = (v - mu) @ vt[:3].T
    lo, hi = np.percentile(pc, [2, 98], axis=0)
    return mu, vt[:3], lo, hi


@app.get("/api/embedding")
def embedding(day: str):
    run = best_run()
    mu, basis, lo, hi = _pca(run)
    d = _day(day)
    path = EMB_DIR / f"{run}_{str(d)[:4]}.nc"
    if not path.exists():
        raise HTTPException(404, f"no embedding for {d}")
    with xr.open_dataset(path) as ds:
        e = ds["cell"].sel(time=str(d)).values.astype(np.float32)
    from .data import sea_mask
    sea = sea_mask()
    flat = e.reshape(e.shape[0], -1).T
    rgb = np.clip(((flat - mu) @ basis.T - lo) / (hi - lo), 0, 1)
    rgb = (rgb * 255).astype(np.uint8).reshape(config.NLAT, config.NLON, 3)
    rgb[~sea] = 0
    return {"day": day, "run": run, "shape": [config.NLAT, config.NLON], "dims": int(e.shape[0]),
            "rgb": b64(rgb, np.uint8), "sea": b64(sea, np.uint8)}


@lru_cache(maxsize=1)
def _casts() -> list[dict]:
    path = config.DATA / "eval-profiles.json"
    return json.loads(path.read_text()) if path.exists() else []


@app.get("/api/casts")
def casts(day: str, window: int = 3):
    d = _day(day)
    out = [c for c in _casts()
           if abs((np.datetime64(c["day"]) - d).astype(int)) <= window]
    return {"day": day, "window_days": window, "casts": out}


@app.get("/api/column")
def column(day: str, lat: float, lon: float):
    j = int(np.clip(np.floor((lat - config.LAT_EDGES[0]) / config.RES), 0, config.NLAT - 1))
    i = int(np.clip(np.floor((lon - config.LON_EDGES[0]) / config.RES), 0, config.NLON - 1))
    out = {}
    for name in ("oceanembed", "glorys", "climatology"):
        try:
            v = field(name, day)[:, j, i]
            out[name] = [None if not np.isfinite(x) else round(float(x), 3) for x in v]
        except HTTPException:
            pass
    return {"day": day, "lat": float(config.LAT[j]), "lon": float(config.LON[i]),
            "depths": config.DEPTHS.tolist(), "profiles": out,
            "seafloor": None if not np.isfinite(seafloor()[j, i]) else float(seafloor()[j, i])}


@app.get("/api/eval")
def evaluation():
    path = config.DATA / "eval-latest.json"
    if not path.exists():
        raise HTTPException(404, "the harness has not run")
    return json.loads(path.read_text())


if VIEWER.exists():
    app.mount("/assets", StaticFiles(directory=VIEWER / "assets"), name="assets")
    if (VIEWER / "cesium").exists():
        app.mount("/cesium", StaticFiles(directory=VIEWER / "cesium"), name="cesium")

    @app.get("/")
    def index():
        return FileResponse(VIEWER / "index.html")
