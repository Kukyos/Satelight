"""The eval harness. The only thing that writes numbers anyone may quote.

    python -m satelight.evaluate

writes docs/13-eval-results.md, data/eval-latest.json and data/eval-profiles.json.

Validation against independent observations (problem statement item 7, E5), on the test
block only, which nothing in training or model selection has seen:

1. **Argo profiles.** Every core Argo temperature cast in the box during the test block.
   Each cast is compared at the model cell and day that contain it, on the 15 depths.
   A cast is interpolated onto those depths linearly between its QC-accepted levels,
   never extrapolated past its shallowest or deepest good level, and never across a gap
   wider than max(25 m, 0.2 x depth). Casts with no accepted level are counted as
   rejected, never dropped silently (hard rule 2).
2. **INCOIS gridded Argo** (ERDDAP `incois_argo_10d_VAM`, substituted for the unnamed
   LAS, D-03), at its own 1 deg / ~10-day resolution: our daily 0.25 deg output is
   averaged *down* to it, never the reverse (L6).

Every score is reported per depth and per basin, beside climatology (the floor) and
GLORYS itself (the ceiling), on exactly the same comparison points (hard rule 8).
GLORYS assimilated these same Argo profiles, so its row is a ceiling, not a rival (L1).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from . import argo, baselines, config, data, grid

DOCS = config.ROOT / "docs" / "13-eval-results.md"
JSON = config.DATA / "eval-latest.json"
PROFILES = config.DATA / "eval-profiles.json"
REGIONS = {"North Indian Ocean (whole box)": None, **config.BASINS}
SURFACE_MAX = 5.5   # m: Argo's shallowest good level, taken as 0 m if it is this shallow

# ------------------------------------------------------------------ Argo -> 15 depths


def profile_on_depths(depth: np.ndarray, value: np.ndarray, accepted: np.ndarray) -> np.ndarray:
    """One cast onto the 15 target depths. NaN wherever the rules forbid a value."""
    ok = accepted & np.isfinite(depth) & np.isfinite(value)
    z, v = depth[ok], value[ok]
    out = np.full(config.DEPTHS.size, np.nan)
    if z.size == 0:
        return out
    order = np.argsort(z)
    z, v = z[order], v[order]
    for k, d in enumerate(config.DEPTHS):
        if d == 0:
            if z[0] <= SURFACE_MAX:
                out[k] = v[0]
            continue
        if d < z[0] or d > z[-1]:
            continue
        j = int(np.searchsorted(z, d))
        if z[j] == d:
            out[k] = v[j]
            continue
        if z[j] - z[j - 1] > max(25.0, 0.2 * d):
            continue
        w = (d - z[j - 1]) / (z[j] - z[j - 1])
        out[k] = (1 - w) * v[j - 1] + w * v[j]
    return out


def in_region(lon: float, lat: float, name: str) -> bool:
    box = REGIONS[name]
    return box is None or (box["lon"][0] <= lon <= box["lon"][1]
                           and box["lat"][0] <= lat <= box["lat"][1])


# ------------------------------------------------------------------ the contenders


def model_runs() -> list[str]:
    """Every trained run except development runs, which exist only to choose the recipe
    on the validation block and are never scored on the test block."""
    import tomllib
    out = []
    for p in config.RUNS.glob("*/best.pt"):
        role = tomllib.loads((p.parent / "config.toml").read_text()).get("role", "candidate")
        if role != "development":
            out.append(p.parent.name)
    return sorted(out)


ROLE_NOTE = {
    "candidate": "a candidate for the model",
    "ablation": "ablation: an input removed, to measure what it adds",
    "comparison": "extended-window comparison: trained from 1993, where salinity before "
                  "~2010 is not satellite salinity; never shown as the model",
}


def selection() -> dict:
    """The headline model, chosen on the validation block only (hard rule 6), before any
    test number is computed: the candidate with the lowest validation RMSE in degrees C,
    averaged over the 15 depths, at its best epoch. Normalised losses are not compared
    across runs: each target (absolute or anomaly) is normalised by its own spread."""
    from .train import load_config

    runs, development = {}, {}
    for p in sorted(config.RUNS.glob("dev-*/history.json")):
        hist = json.loads(p.read_text())
        cfg = load_config(p.parent / "config.toml")
        best = min(hist, key=lambda h: h["val_loss"])
        development[p.parent.name] = {
            "target": cfg["target"], "lags": cfg["lags"], "crop": cfg.get("crop"),
            "dropout": cfg.get("dropout", 0.0), "wd": cfg.get("wd", 1e-4),
            "noise": cfg.get("noise", 0.0), "epochs_run": len(hist),
            "best_epoch": best["epoch"], "val_loss": best["val_loss"],
            "val_rmse_per_depth": best["val_rmse_per_depth"]}
    for run in model_runs():
        cfg = load_config(config.RUNS / run / "config.toml")
        hist = json.loads((config.RUNS / run / "history.json").read_text())
        best = min(hist, key=lambda h: h["val_loss"])
        runs[run] = {"role": cfg.get("role", "candidate"), "arch": cfg["arch"],
                     "target": cfg["target"],
                     "val_rmse_mean": float(np.mean(best["val_rmse_per_depth"])),
                     "lags": cfg["lags"], "inputs": cfg["inputs"], "epochs_run": len(hist),
                     "best_epoch": best["epoch"], "val_loss": best["val_loss"],
                     "val_rmse_per_depth": best["val_rmse_per_depth"]}
    candidates = {k: v for k, v in runs.items() if v["role"] == "candidate"}
    headline = min(candidates, key=lambda k: candidates[k]["val_rmse_mean"]) if candidates else None
    return {"rule": "lowest validation RMSE (°C, mean over the 15 depths, at the best epoch) "
                    "among candidates (validation block only)",
            "headline": headline, "runs": runs, "development": development}


def label(name: str, sel: dict) -> str:
    """How a contender is named in the tables: the headline says so; ablations and the
    extended-window comparison say what they are."""
    r = sel["runs"].get(name)
    if r is None:
        return name
    if name == sel["headline"]:
        return f"{name} (selected)"
    return f"{name} ({r['role']})" if r["role"] != "candidate" else name


def contenders() -> tuple[dict, np.ndarray]:
    """Every predictor on the test block: name -> (T, 15, H, W), on one shared day axis."""
    from .predict import level_mask, predict_span

    a, b = config.SPLITS["test"]
    x, y, t = data.load_raw("test", config.INPUTS)
    out = {"climatology": (baselines.climatology(t), t)}
    if (config.RUNS / "linear" / "coef.npy").exists():
        out["linear"] = (baselines.linear(x, t), t)
    del x
    for run in model_runs():
        p, tp, _ = predict_span(run, a, b)
        out[run] = (p, tp)
    out["GLORYS (ceiling)"] = (y, t)
    common = t
    for _, tp in out.values():
        common = np.intersect1d(common, tp)
    mask = level_mask()
    aligned = {}
    for k, (p, tp) in out.items():
        idx = np.searchsorted(tp, common)
        q = p[idx]
        q[:, ~mask] = np.nan
        aligned[k] = q
    return aligned, common


# ------------------------------------------------------------------ metrics


def scores(pred: np.ndarray, obs: np.ndarray, clim: np.ndarray | None) -> dict:
    n = obs.size
    if n < 3:
        return {"n": n}
    err = pred - obs
    out = {"n": int(n), "rmse": float(np.sqrt(np.mean(err ** 2))), "bias": float(err.mean()),
           "r": float(np.corrcoef(pred, obs)[0, 1])}
    if clim is not None:
        a, b = pred - clim, obs - clim
        if a.std() > 1e-6 and b.std() > 1e-6:
            out["anomaly_r"] = float(np.corrcoef(a, b)[0, 1])
    return out


def argo_block(aligned: dict, t: np.ndarray, sea: np.ndarray):
    a, b = config.SPLITS["test"]
    casts = argo.load_period(a, b)
    counts = {"casts_found": len(casts), "casts_rejected_no_good_level": 0,
              "casts_outside_sea_mask": 0, "casts_off_test_days": 0,
              "levels_rejected_by_qc": int(sum(c.n_rejected for c in casts)),
              "casts_used": 0}
    rows, meta = [], []
    for c in casts:
        if not c.accepted.any():
            counts["casts_rejected_no_good_level"] += 1
            continue
        i = int(np.floor((c.lon - config.LON_EDGES[0]) / config.RES))
        j = int(np.floor((c.lat - config.LAT_EDGES[0]) / config.RES))
        if not (0 <= i < config.NLON and 0 <= j < config.NLAT) or not sea[j, i]:
            counts["casts_outside_sea_mask"] += 1
            continue
        d = np.searchsorted(t, np.datetime64(c.time, "D"))
        if d >= t.size or t[d] != np.datetime64(c.time, "D"):
            counts["casts_off_test_days"] += 1
            continue
        obs = profile_on_depths(c.depth, c.value, c.accepted)
        if not np.isfinite(obs).any():
            counts["casts_rejected_no_good_level"] += 1
            continue
        counts["casts_used"] += 1
        rows.append((d, j, i, obs))
        meta.append({"platform": c.platform, "cycle": getattr(c, "cycle", None),
                     "lat": round(float(c.lat), 3), "lon": round(float(c.lon), 3),
                     "day": str(t[d]), "data_mode": c.data_mode,
                     "source_file": c.source_file, "levels_rejected": c.n_rejected})
    obs = np.array([r[3] for r in rows])                                  # (P, 15)
    vals = {k: np.array([v[d, :, j, i] for d, j, i, _ in rows]) for k, v in aligned.items()}
    # One comparison set for everyone: a (cast, depth) counts only where the cast and
    # every contender have a value, so no row is scored on easier points than another.
    common = np.isfinite(obs)
    for v in vals.values():
        common &= np.isfinite(v)
    table = {}
    for region in REGIONS:
        inside = np.array([in_region(m["lon"], m["lat"], region) for m in meta])
        table[region] = {}
        for name, v in vals.items():
            per = []
            for k in range(config.DEPTHS.size):
                sel = common[:, k] & inside
                clim = vals["climatology"][sel, k] if name != "climatology" else None
                per.append(scores(v[sel, k], obs[sel, k], clim))
            table[region][name] = per
    for m, o, r in zip(meta, obs, range(len(meta))):
        m["obs"] = [None if not np.isfinite(x) else round(float(x), 3) for x in o]
        m["pred"] = {k: [None if not np.isfinite(x) else round(float(x), 3) for x in v[r]]
                     for k, v in vals.items()}
    return table, counts, meta


# ------------------------------------------------------------------ INCOIS gridded Argo


def incois_block(aligned: dict, t: np.ndarray, casts: list[dict] | None = None) -> dict:
    """Compare everyone with INCOIS's gridded Argo at its own 1 deg / 10-day grid.

    INCOIS values outside the Argo global range are rejected and counted (hard rule 2).
    With the test-block casts given, INCOIS itself is also scored against them, beside
    GLORYS brought to the same 1 deg / 10-day grid, so the reader can see how well the
    reference agrees with the Argo it is built from."""
    import gsw
    import requests
    import truststore
    import xarray as xr

    truststore.inject_into_ssl()
    a, b = config.SPLITS["test"]
    cache = config.CACHE / "incois"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"vam_{a}_{b}.nc"
    if not path.exists():
        span = (f"[({a}T00:00:00Z):1:({b}T00:00:00Z)][(5.0):1:(1000.0)]"
                f"[({config.LAT_EDGES[0] + 0.5}):1:({config.LAT_EDGES[1] - 0.5})]"
                f"[({config.LON_EDGES[0] + 0.5}):1:({config.LON_EDGES[1] - 0.5})]")
        url = (f"https://erddap.incois.gov.in/erddap/griddap/incois_argo_10d_VAM.nc?"
               f"TEMP{span},SAL{span}")
        r = requests.get(url, timeout=600)
        if r.status_code != 200:
            raise RuntimeError(f"INCOIS ERDDAP {r.status_code}: {r.text[:300]}")
        path.write_bytes(r.content)
    ds = xr.open_dataset(path)
    levels = [float(z) for z in ds["ZAX"].values]
    shared = [z for z in levels if np.isclose(config.DEPTHS, z).any()]
    notes = [
        "INCOIS TEMP is labelled 'degs'; read as degree_Celsius (in-situ temperature)",
        "INCOIS in-situ temperature converted to potential temperature with gsw.pt0_from_t "
        "and INCOIS's own SAL, to match GLORYS thetao and our output",
        "each INCOIS step is compared with the mean of our daily fields over the 10 days "
        "centred on its timestamp (+/-5 d)",
        "our 0.25 deg cells are averaged to INCOIS's 1 deg cells (4 x 4 exact block mean, "
        f"cells with < {config.OCEAN_FRACTION_MIN:.0%} valid area left out)",
        f"compared at the depths both grids have: {shared}",
    ]
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    temp_all, sal_all = ds["TEMP"].values, ds["SAL"].values
    bad = np.isfinite(temp_all) & ((temp_all < -2.5) | (temp_all > 40.0) |
                                   ~((sal_all >= 2.0) & (sal_all <= 41.0)))
    qc = {"values": int(np.isfinite(temp_all).sum()), "rejected_by_range": int(bad.sum())}
    notes.append(f"range test (Argo global range: T -2.5..40 degC, S 2..41): "
                 f"{qc['rejected_by_range']} of {qc['values']} INCOIS values rejected")
    temp_all = np.where(bad, np.nan, temp_all)
    st = grid.Stencil((1.0,) * 4, 4, "4 x 4 block mean to 1 deg")
    steps = ds["time"].values.astype("datetime64[D]")
    by_step = {}   # INCOIS step -> casts inside its window, on INCOIS's 1 deg cells
    for c in casts or []:
        day = np.datetime64(c["day"])
        s = np.flatnonzero((day >= steps - 5) & (day < steps + 5))
        j = int(np.floor(c["lat"] - config.LAT_EDGES[0]))
        i = int(np.floor(c["lon"] - config.LON_EDGES[0]))
        if s.size and 0 <= j < lat.size and 0 <= i < lon.size:
            obs = np.array([np.nan if x is None else x for x in c["obs"]])
            by_step.setdefault(int(s[0]), []).append((j, i, obs))
    ref = {k: ([], [], []) for k in range(config.DEPTHS.size)}   # obs, INCOIS, GLORYS
    table = {}
    obs_all, pred_all, where_all = [], {k: [] for k in aligned}, []
    for s, ts in enumerate(steps):
        win = (t >= ts - 5) & (t < ts + 5)
        if win.sum() < 8:
            continue
        for z in shared:
            k = int(np.flatnonzero(np.isclose(config.DEPTHS, z))[0])
            zi = int(np.flatnonzero(np.isclose(ds["ZAX"].values, z))[0])
            temp, sal = temp_all[s, zi], sal_all[s, zi]
            p = gsw.p_from_z(-z, lat[:, None])
            sa = gsw.SA_from_SP(sal, p, lon[None, :], lat[:, None])
            pt = gsw.pt0_from_t(sa, temp, p)
            coarse = {}
            for name, v in aligned.items():
                m, share = grid.regrid(np.nanmean(v[win, k], axis=0), st, lat.size, lon.size)
                m[share < config.OCEAN_FRACTION_MIN] = np.nan
                coarse[name] = m
            for j, i, obs in by_step.get(s, []):
                g = coarse.get("GLORYS (ceiling)")
                if g is not None and np.isfinite([obs[k], pt[j, i], g[j, i]]).all():
                    ref[k][0].append(obs[k]); ref[k][1].append(pt[j, i]); ref[k][2].append(g[j, i])
            ok = np.isfinite(pt)
            for m in coarse.values():
                ok &= np.isfinite(m)
            obs_all.append(pt[ok])
            for name in aligned:
                pred_all[name].append(coarse[name][ok])
            jj, ii = np.nonzero(ok)
            where_all.append(np.stack([np.full(jj.size, k), lat[jj], lon[ii]], 1))
    obs = np.concatenate(obs_all)
    where = np.concatenate(where_all)
    preds = {k: np.concatenate(v) for k, v in pred_all.items()}
    for region in REGIONS:
        inside = np.array([in_region(lo, la, region) for _, la, lo in where])
        table[region] = {}
        for name, v in preds.items():
            per = []
            for k in range(config.DEPTHS.size):
                sel = inside & (where[:, 0] == k)
                clim = preds["climatology"][sel] if name != "climatology" else None
                per.append(scores(v[sel], obs[sel], clim) if sel.any() else {"n": 0})
            table[region][name] = per
    reference = [{"n": len(o), "incois": scores(np.array(a), np.array(o), None),
                  "glorys": scores(np.array(g), np.array(o), None)} if o else {"n": 0}
                 for o, a, g in ref.values()]
    return {"table": table, "notes": notes, "shared_depths": shared, "file": path.name,
            "qc": qc, "reference_vs_argo": reference}


# ------------------------------------------------------------------ what a cyclone feeds on


def isotherm_depth(t: np.ndarray, iso: float) -> float:
    """Depth (m) where a 15-level profile first cools through `iso`, linear between
    levels. NaN if the surface is already colder, the profile never gets that cold, or a
    level above the crossing is missing: nothing is guessed past the data."""
    z = config.DEPTHS
    if not np.isfinite(t[0]) or t[0] <= iso:
        return np.nan
    for k in range(z.size - 1):
        if not np.isfinite(t[k + 1]):
            return np.nan
        if t[k + 1] <= iso:
            return float(z[k] + (t[k] - iso) / (t[k] - t[k + 1]) * (z[k + 1] - z[k]))
    return np.nan


def tchp(t: np.ndarray) -> float:
    """Tropical cyclone heat potential, kJ/cm^2: rho cp times the integral of (T - 26)
    from the surface down to the 26 degC isotherm, trapezoidal on the 15 levels. Zero when
    the surface is at or below 26 degC; NaN (unknown, not zero, not a lower bound) when
    the profile never cools to 26 degC or a level above the crossing is missing."""
    z, a = config.DEPTHS, t - config.TCHP_T
    if not np.isfinite(a[0]):
        return np.nan
    if a[0] <= 0:
        return 0.0
    area = 0.0
    for k in range(z.size - 1):
        if not np.isfinite(a[k + 1]):
            return np.nan
        if a[k + 1] > 0:
            area += 0.5 * (a[k] + a[k + 1]) * (z[k + 1] - z[k])
        else:
            area += 0.5 * a[k] * (a[k] / (a[k] - a[k + 1])) * (z[k + 1] - z[k])
            return float(config.RHO_REF * config.CP0 * area / 1e7)
    return np.nan


def mld(t: np.ndarray, dt: float = 0.2, ref: float = 10.0) -> float:
    """Mixed-layer depth (m), temperature criterion: the first depth below `ref` where the
    temperature differs from its value at `ref` by more than `dt` (de Boyer Montegut et al.
    2004, JGR 109, C12003: 0.2 degC from 10 m), linear between levels. The top of a
    sonar's surface duct follows it. NaN if 10 m is missing, the column never departs by
    dt, or a level above the crossing is missing. On the 15 standard levels it resolves
    tens of metres, not metres (said wherever it is shown)."""
    z = config.DEPTHS
    k0 = int(np.flatnonzero(z == ref)[0])
    t0 = t[k0]
    if not np.isfinite(t0):
        return np.nan
    for k in range(k0, z.size - 1):
        if not np.isfinite(t[k + 1]):
            return np.nan
        d0, d1 = abs(t[k] - t0), abs(t[k + 1] - t0)
        if d1 > dt:
            return float(z[k] + (dt - d0) / (d1 - d0) * (z[k + 1] - z[k]))
    return np.nan


HAZARD = {"D20 (m)": lambda t: isotherm_depth(t, 20.0),
          "D26 (m)": lambda t: isotherm_depth(t, 26.0),
          "TCHP (kJ/cm²)": tchp,
          "MLD (m)": mld}


def heatwave_block(meta: list[dict]) -> dict:
    """Hidden heatwaves (heatwave.py) on the Argo casts: for each cast and each contender,
    is the 50-150 m layer above its 90th percentile for that day and cell, and is it hidden
    (the surface at or below its own)? Scored as a yes/no forecast of the cast's own flag:
    hits, misses, false alarms, probability of detection, false alarm ratio, and the Heidke
    skill score (0 = no better than chance). One day per cast, so no duration test."""
    from . import heatwave
    from .baselines import _doy
    names = list(meta[0]["pred"])
    arr = lambda v: np.array([np.nan if x is None else x for x in v])
    rows = []
    for m in meta:
        j = int(np.floor((m["lat"] - config.LAT_EDGES[0]) / config.RES))
        i = int(np.floor((m["lon"] - config.LON_EDGES[0]) / config.RES))
        d = int(_doy(np.array([np.datetime64(m["day"])]))[0])
        rows.append((heatwave.hidden(arr(m["obs"]), d, j, i),
                     {n: heatwave.hidden(arr(m["pred"][n]), d, j, i) for n in names}))
    out = {}
    for e, what in ((0, "Warm 50–150 m layer"), (1, "Hidden: warm layer, normal surface")):
        obs = np.array([r[0][e] for r in rows])
        vals = {n: np.array([r[1][n][e] for r in rows]) for n in names}
        ok = np.isfinite(obs)
        for v in vals.values():
            ok &= np.isfinite(v)
        out[what] = {}
        for region in REGIONS:
            sel = ok & np.array([in_region(m["lon"], m["lat"], region) for m in meta])
            o = obs[sel] > 0.5
            out[what][region] = {"n": int(sel.sum()), "observed": int(o.sum()), "by": {}}
            for n, v in vals.items():
                f = v[sel] > 0.5
                a, b, c = int((f & o).sum()), int((f & ~o).sum()), int((~f & o).sum())
                dd = int((~f & ~o).sum())
                tot = a + b + c + dd
                exp = ((a + c) * (a + b) + (b + dd) * (c + dd)) / tot if tot else 0
                out[what][region]["by"][n] = {
                    "hits": a, "false_alarms": b, "misses": c,
                    "pod": a / (a + c) if a + c else None,
                    "far": b / (a + b) if a + b else None,
                    "hss": (a + dd - exp) / (tot - exp) if tot - exp else None}
    return out


def hazard_block(meta: list[dict]) -> dict:
    """The 20 and 26 degC isotherm depths and the heat potential, from each contender's
    15 levels and from the Argo cast on the same 15 levels, scored per region. As in the
    temperature tables, a cast counts only where the cast and every contender have a value."""
    names = list(meta[0]["pred"])
    out = {}
    for q, f in HAZARD.items():
        obs = np.array([f(np.array([np.nan if x is None else x for x in m["obs"]])) for m in meta])
        vals = {n: np.array([f(np.array([np.nan if x is None else x for x in m["pred"][n]]))
                             for m in meta]) for n in names}
        ok = np.isfinite(obs)
        for v in vals.values():
            ok &= np.isfinite(v)
        out[q] = {}
        for region in REGIONS:
            sel = ok & np.array([in_region(m["lon"], m["lat"], region) for m in meta])
            out[q][region] = {n: {**scores(v[sel], obs[sel], None),
                                  "obs_mean": float(obs[sel].mean()) if sel.any() else None}
                              for n, v in vals.items()}
    return out


def gap_closed(table: dict) -> dict:
    """Share of the gap between the floor and the ceiling that a contender closes, per
    depth and region: (RMSE climatology - RMSE model) / (RMSE climatology - RMSE GLORYS).
    1 means as close to Argo as GLORYS, 0 no better than climatology, negative worse.
    None where GLORYS is not better than climatology, so there is no gap to close."""
    out = {}
    for region, by in table.items():
        c, g = by["climatology"], by["GLORYS (ceiling)"]
        out[region] = {}
        for name in by:
            if name in ("climatology", "GLORYS (ceiling)"):
                continue
            row = []
            for k in range(config.DEPTHS.size):
                cr, gr, mr = c[k].get("rmse"), g[k].get("rmse"), by[name][k].get("rmse")
                row.append(None if None in (cr, gr, mr) or cr - gr <= 1e-9
                           else float((cr - mr) / (cr - gr)))
            out[region][name] = row
    return out


def cyclone_block(aligned: dict, t: np.ndarray, headline_label: str) -> dict:
    """Each cyclone's wake: the change in box-mean temperature per depth between 3 days
    before the depression and 3 days after landfall, in the reconstruction, in GLORYS
    and in climatology (whose change is only the season). A case study beside the Argo
    scores, not a validation: GLORYS is the training target. Also writes a map figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = {}
    show = {"reconstruction": headline_label, "GLORYS": "GLORYS (ceiling)",
            "climatology": "climatology"}
    for name, cy in config.CYCLONES.items():
        pad = np.timedelta64(config.CYCLONE_MARGIN_DAYS, "D")
        d0 = np.datetime64(cy["depression"]) - pad
        d1 = np.datetime64(cy["landfall"]) + pad
        i0, i1 = np.searchsorted(t, d0), np.searchsorted(t, d1)
        if i0 >= t.size or i1 >= t.size or t[i0] != d0 or t[i1] != d1:
            out[name] = {"error": f"{d0} or {d1} not in the scored days"}
            continue
        jj = (config.LAT >= cy["lat"][0]) & (config.LAT <= cy["lat"][1])
        ii = (config.LON >= cy["lon"][0]) & (config.LON <= cy["lon"][1])
        rec = {"before": str(d0), "after": str(d1), "box": {"lon": cy["lon"], "lat": cy["lat"]},
               "source": cy["source"], "change": {}, "before_mean": {}}
        for key, lab in show.items():
            v = aligned[lab]
            a, b = v[i0][:, jj][:, :, ii], v[i1][:, jj][:, :, ii]
            both = np.isfinite(a) & np.isfinite(b)
            rec["change"][key] = [float((b[k] - a[k])[both[k]].mean()) if both[k].any() else None
                                  for k in range(config.DEPTHS.size)]
            rec["before_mean"][key] = [float(a[k][both[k]].mean()) if both[k].any() else None
                                       for k in range(config.DEPTHS.size)]
        rec["tchp_box_mean"] = {}
        for key, lab in show.items():
            v = aligned[lab]
            col = lambda day: np.array([[tchp(v[day][:, j, i]) for i in np.flatnonzero(ii)]
                                        for j in np.flatnonzero(jj)])
            a, b = col(i0), col(i1)
            both = np.isfinite(a) & np.isfinite(b)
            rec["tchp_box_mean"][key] = {"before": float(a[both].mean()), "after": float(b[both].mean()),
                                         "cells": int(both.sum())}
        # Map: change at 0 m and 50 m, reconstruction beside GLORYS, one symmetric scale.
        ks = [int(np.flatnonzero(config.DEPTHS == d)[0]) for d in (0, 50)]
        fig, axs = plt.subplots(2, 2, figsize=(9, 7.2), constrained_layout=True)
        lim = 3.0
        for r, k in enumerate(ks):
            for c, lab in enumerate([headline_label, "GLORYS (ceiling)"]):
                v = aligned[lab]
                dv = v[i1, k] - v[i0, k]
                ax = axs[r, c]
                im = ax.pcolormesh(config.LON, config.LAT, dv, cmap="RdBu_r", vmin=-lim, vmax=lim,
                                   shading="nearest")
                ax.add_patch(plt.Rectangle((cy["lon"][0], cy["lat"][0]),
                                           cy["lon"][1] - cy["lon"][0], cy["lat"][1] - cy["lat"][0],
                                           fill=False, ec="k", lw=1, ls="--"))
                span = 6.0
                ax.set_xlim(cy["lon"][0] - span, cy["lon"][1] + span)
                ax.set_ylim(max(5, cy["lat"][0] - span), min(30, cy["lat"][1] + span))
                ax.set_facecolor("#8a8a8a")
                who = "Reconstruction (satellites only)" if lab == headline_label else "GLORYS (target)"
                ax.set_title(f"{who}, {config.DEPTHS[k]:.0f} m", fontsize=10)
        fig.colorbar(im, ax=axs, shrink=0.8, label=f"°C, {d1} minus {d0}")
        fig.suptitle(f"Cyclone {name}: temperature change across the storm")
        fname = f"cyclone_{name.lower()}.png"
        fig.savefig(config.DATA / "figures" / fname, dpi=150)
        plt.close(fig)
        rec["figure"] = fname
        out[name] = rec
    return out


# ------------------------------------------------------------------ report


def _fmt(s: dict, key: str) -> str:
    v = s.get(key)
    return "—" if v is None else f"{v:+.3f}" if key == "bias" else f"{v:.3f}"


def _tables(table: dict, title: str) -> list[str]:
    lines = []
    for region, by_model in table.items():
        names = list(by_model)
        for key, label in (("rmse", "RMSE (°C)"), ("bias", "Bias, model − obs (°C)"),
                           ("r", "Correlation r"), ("anomaly_r", "Anomaly correlation vs climatology")):
            lines += [f"#### {title} · {region} · {label}", "",
                      "| Depth (m) | N | " + " | ".join(names) + " |",
                      "|---:|---:|" + "---:|" * len(names)]
            for k, d in enumerate(config.DEPTHS):
                n = by_model[names[0]][k].get("n", 0)
                lines.append(f"| {d:.0f} | {n} | " +
                             " | ".join(_fmt(by_model[m][k], key) for m in names) + " |")
            lines.append("")
    return lines


def _novelty_lines(result: dict) -> list[str]:
    lines = []
    g = result.get("gap_closed")
    if g:
        lines += ["## Share of the floor-to-ceiling gap closed (Argo, test block)", "",
                  "(RMSE climatology − RMSE model) / (RMSE climatology − RMSE GLORYS), from the "
                  "RMSE tables above. 1 = as close to Argo as GLORYS; 0 = no better than "
                  "climatology; negative = worse than climatology; — = GLORYS is not better "
                  "than climatology there, so there is no gap.", ""]
        for region, by in g.items():
            names = list(by)
            lines += [f"#### {region}", "", "| Depth (m) | " + " | ".join(names) + " |",
                      "|---:|" + "---:|" * len(names)]
            for k, d in enumerate(config.DEPTHS):
                lines.append(f"| {d:.0f} | " + " | ".join(
                    "—" if by[n][k] is None else f"{by[n][k]:.2f}" for n in names) + " |")
            lines.append("")
    h = result.get("hazard")
    if h:
        lines += ["## Isotherm depths, heat potential and the mixed layer (Argo, test block)", "",
                  "Computed from each contender's 15 levels and from the Argo cast on the same "
                  "15 levels. D20 is the core of the thermocline; TCHP is the heat above 26 °C "
                  "(Leipper and Volgenau 1972), "
                  f"ρ = {config.RHO_REF} kg/m³, cp = TEOS-10 cp0. MLD is the first depth below "
                  "10 m more than 0.2 °C from the 10 m temperature (de Boyer Montégut et al. "
                  "2004), resolved only as finely as the 15 levels. A cast whose profile never "
                  "reaches the threshold, or has a gap above it, has no value and is left out, "
                  "for every contender alike.", ""]
        for q, by_region in h.items():
            for region, by in by_region.items():
                names = list(by)
                n = by[names[0]].get("n", 0)
                lines += [f"#### {q} · {region} · N = {n} casts, Argo mean "
                          + ("—" if by[names[0]].get("obs_mean") is None else f"{by[names[0]]['obs_mean']:.1f}"),
                          "", "| Measure | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
                for key in ("rmse", "bias", "r"):
                    lines.append(f"| {key} | " + " | ".join(_fmt(by[m], key) for m in names) + " |")
                lines.append("")
    hw = result.get("heatwave")
    if hw:
        lines += ["## Hidden heatwaves (Argo, test block)", "",
                  "The 50–150 m layer mean above its 90th percentile for that day of year and "
                  "cell (GLORYS training years, ±5-day window; Hobday et al. 2016), and hidden "
                  "when the 0 m temperature is at or below its own 90th percentile. Each "
                  "contender's flag is scored against the Argo cast's own flag, on the same "
                  "casts. One day per cast: Hobday's 5-day minimum cannot be tested on a cast. "
                  "POD = probability of detection, FAR = false alarm ratio, HSS = Heidke skill "
                  "score (0 is chance, 1 perfect). Climatology never exceeds its own percentile, "
                  "so it never flags.", ""]
        f = lambda x: "—" if x is None else f"{x:.2f}"
        for what, by_region in hw.items():
            for region, r in by_region.items():
                lines += [f"#### {what} · {region} · N = {r['n']} casts, {r['observed']} flagged by Argo",
                          "", "| Contender | hits | false alarms | misses | POD | FAR | HSS |",
                          "|---|---:|---:|---:|---:|---:|---:|"]
                for n, v in r["by"].items():
                    lines.append(f"| {n} | {v['hits']} | {v['false_alarms']} | {v['misses']} | "
                                 f"{f(v['pod'])} | {f(v['far'])} | {f(v['hss'])} |")
                lines.append("")
    cy = result.get("cyclones")
    if cy:
        lines += ["## Cyclone wakes in the test block (case study, not validation)", "",
                  "Change in box-mean temperature from 3 days before the depression to 3 days "
                  "after landfall. GLORYS is the training target, so this shows whether the "
                  "satellite-only reconstruction carries the storm's cooling; climatology's "
                  "change is the season alone.", ""]
        for name, r in cy.items():
            if "error" in r:
                lines += [f"### {name}", "", f"Not computed: {r['error']}", ""]
                continue
            lines += [f"### {name} · {r['before']} → {r['after']} · box {r['box']['lon']}°E, "
                      f"{r['box']['lat']}°N", "", f"Dates: {r['source']}.", "",
                      "| Depth (m) | reconstruction | GLORYS | climatology |", "|---:|---:|---:|---:|"]
            for k, d in enumerate(config.DEPTHS):
                row = [r["change"][x][k] for x in ("reconstruction", "GLORYS", "climatology")]
                lines.append(f"| {d:.0f} | " + " | ".join("—" if v is None else f"{v:+.2f}" for v in row) + " |")
            lines += ["", "| Box-mean TCHP (kJ/cm²) | before | after | cells |", "|---|---:|---:|---:|",
                      *[f"| {x} | {v['before']:.1f} | {v['after']:.1f} | {v['cells']} |"
                        for x, v in r["tchp_box_mean"].items()],
                      "", f"Figure: `data/figures/{r['figure']}`", ""]
    return lines


def report(result: dict) -> str:
    c = result["argo_counts"]
    lines = [
        "# Eval results — generated, never hand-edited",
        "",
        f"Generated by `python -m satelight.evaluate` on {result['generated']}. "
        "Every number quoted anywhere in this project traces to this file or "
        "`data/eval-latest.json`.",
        "",
        "## Setup",
        "",
        f"- Window {config.WINDOW[0]} → {config.WINDOW[1]}; splits (contiguous, "
        + ", ".join(f"{k} {a} → {b}" for k, (a, b) in config.SPLITS.items()) + ").",
        f"- Test days scored: {result['test_days']}.",
        f"- Contenders: {', '.join(result['contenders'])}. `climatology` is the floor; "
        "`GLORYS (ceiling)` is the training target itself, which assimilated these Argo "
        "casts, so it is a ceiling, not a rival.",
        "- Every contender is scored on the same (cast, depth) points: a point counts only "
        "where the cast and every contender have a value.",
        "",
        "## Model selection (validation block only, fixed before scoring)",
        "",
        f"Rule: {result['selection']['rule']}. Headline model: "
        f"**{result['selection']['headline']}**.",
        "",
        "Val loss is normalised by each target's own spread, so it is shown but not compared "
        "across targets; the RMSE columns are in °C.",
        "",
        "| Run | Role | Encoder | Target | Lags (days) | Inputs | Best epoch | Val loss | Val RMSE mean (°C) | Val RMSE 0 / 100 / 300 / 1000 m (°C) |",
        "|---|---|---|---|---|---|---:|---:|---:|---|",
        *[f"| {k} | {ROLE_NOTE.get(v['role'], v['role'])} | {v['arch']} | {v['target']} | {v['lags']} | "
          f"{', '.join(v['inputs'])} | {v['best_epoch']}/{v['epochs_run']} | {v['val_loss']:.4f} | "
          f"{v['val_rmse_mean']:.4f} | "
          + " / ".join(f"{v['val_rmse_per_depth'][i]:.3f}" for i in (0, 7, 11, 14)) + " |"
          for k, v in result["selection"]["runs"].items()],
        "",
        "### How the training recipe was chosen (development runs, validation block only)",
        "",
        "Each row is one U-Net run used to choose the recipe; none is scored on the test "
        "block. Val loss is not comparable between the absolute and anomaly targets (it is "
        "normalised by each target's spread); the RMSE columns are.",
        "",
        "| Run | Target | Lags | Crop | Dropout | Weight decay | Noise | Best epoch | Val loss | Val RMSE 0 / 100 / 300 / 1000 m (°C) |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
        *[f"| {k} | {v['target']} | {v['lags']} | {v['crop'] or '—'} | {v['dropout']} | "
          f"{v['wd']} | {v['noise']} | {v['best_epoch']}/{v['epochs_run']} | {v['val_loss']:.4f} | "
          + " / ".join(f"{v['val_rmse_per_depth'][i]:.3f}" for i in (0, 7, 11, 14)) + " |"
          for k, v in result["selection"].get("development", {}).items()],
        "",
        "## Argo casts (test block)",
        "",
        "| Count | Value |", "|---|---:|",
        *[f"| {k.replace('_', ' ')} | {v} |" for k, v in c.items()],
        "",
        *_tables(result["argo"], "Argo"),
        *_novelty_lines(result),
    ]
    if "incois" in result:
        inc = result["incois"]
        lines += ["## INCOIS gridded Argo (`incois_argo_10d_VAM`, 1° / 10-day)", "",
                  *[f"- {n}" for n in inc["notes"]], ""]
        if inc.get("reference_vs_argo"):
            lines += ["### How well the reference itself agrees with Argo", "",
                      "INCOIS's gridded field, and GLORYS averaged to the same 1° / 10-day "
                      "grid, each scored against the test-block Argo casts that fall in the "
                      "cell and the 10-day window (same points for both). Read the tables "
                      "below in this light: where INCOIS agrees with Argo less well than "
                      "GLORYS at its own resolution does, a score against INCOIS measures "
                      "INCOIS as much as the model.", "",
                      "| Depth (m) | N | INCOIS r | INCOIS RMSE | INCOIS bias | GLORYS 1° r | GLORYS 1° RMSE | GLORYS 1° bias |",
                      "|---:|---:|---:|---:|---:|---:|---:|---:|",
                      *[f"| {config.DEPTHS[k]:g} | {r['n']} | {_fmt(r['incois'], 'r')} | "
                        f"{_fmt(r['incois'], 'rmse')} | {_fmt(r['incois'], 'bias')} | "
                        f"{_fmt(r['glorys'], 'r')} | {_fmt(r['glorys'], 'rmse')} | "
                        f"{_fmt(r['glorys'], 'bias')} |"
                        for k, r in enumerate(inc["reference_vs_argo"]) if r["n"]], ""]
        lines += _tables(inc["table"], "INCOIS")
    sc = result.get("embedding_screen")
    if sc:
        lines += ["## Which embedding carries S4 (validation block only, fixed before scoring)", "",
                  f"Rule: {sc['rule']}. Chosen: **{sc['chosen']}**.", "",
                  "| Run | MLD probe R², embedding | MLD probe R², raw features |", "|---|---:|---:|",
                  *[f"| {k} | {v['r2_embedding']:.3f} | {v['r2_raw']:.3f} |"
                    for k, v in sc["runs"].items()], ""]
    for run, e in result.get("embedding", {}).items():
        role = [w for w, r in (("headline", result["selection"]["headline"]),
                               ("carries S4", sc and sc["chosen"])) if r == run]
        lines += [f"## Embedding inspection · {run}" + (f" ({', '.join(role)})" if role else ""), ""]
        if e.get("verdict"):
            lines += ["| S4 check (`02-requirements.md`) | Met |", "|---|---|",
                      *[f"| {k} | {'yes' if v else 'no'} |" for k, v in e["verdict"].items()], ""]
        if "seasons" in e:
            s = e["seasons"]
            lines += ["Daily embeddings, k-means into 4 groups, against the four monsoon "
                      f"seasons over {s['days']} test days:", "",
                      "| Measure | Embedding | Control |", "|---|---:|---:|",
                      f"| NMI, clusters vs season | {s['nmi_clusters_vs_season']:.3f} | "
                      f"{s['nmi_shuffled_seasons']:.3f} (shuffled seasons) |",
                      f"| Nearest-neighbour day in the same season | "
                      f"{s['nearest_neighbour_same_season']:.3f} | "
                      f"{s['nearest_neighbour_chance']:.3f} (chance) |", "",
                      "The encoder is given the day of year, so the day of year alone is the "
                      "control. Clustering (NMI) is the S4 test. Nearest-neighbour is judged "
                      "against chance only: with ±3 days excluded, a smoothly varying "
                      "embedding's nearest neighbour is a few days away and crosses a calendar "
                      "season boundary near each one, while the day-of-year control matches "
                      "the same date a year apart, so it is near 1 by construction "
                      "(`02-requirements.md` S4, amended 2026-09-28).", "",
                      "| Measure | Day of year only |", "|---|---:|",
                      f"| NMI, clusters vs season | "
                      f"{s['day_of_year_control']['nmi_clusters_vs_season']:.3f} |",
                      f"| Nearest-neighbour day in the same season | "
                      f"{s['day_of_year_control']['nearest_neighbour_same_season']:.3f} |", ""]
        if "mld_probe" in e:
            m = e["mld_probe"]
            lines += [f"Linear probe for mixed-layer depth ({m['label']}), fitted on the "
                      f"{m['fit_on']} ({m['rows_fit']} cell-days), scored on the "
                      f"{m['scored_on']} ({m['rows_scored']} cell-days):", "",
                      "| Probe input | R² on test | R² on test anomalies (vs monthly climatology) |",
                      "|---|---:|---:|",
                      *[f"| {k} | {v['r2_test']:.3f} | {v['r2_test_anomaly']:.3f} |"
                        for k, v in m.items() if isinstance(v, dict)], ""]
        if "mld_probe_error" in e:
            lines += [f"MLD probe not run: {e['mld_probe_error']}", ""]
        if e.get("figures"):
            lines += ["Figures: " + ", ".join(f"`data/figures/{f}`" for f in e["figures"]), ""]
    if "incois_error" in result:
        lines += ["## INCOIS gridded Argo", "", f"Not scored this run: {result['incois_error']}", ""]
    return "\n".join(lines) + "\n"


def run() -> dict:
    t0 = time.time()
    sel = selection()   # fixed from the validation block before anything is scored
    sea = data.sea_mask()
    aligned, t = contenders()
    aligned = {label(k, sel): v for k, v in aligned.items()}
    table, counts, meta = argo_block(aligned, t, sea)
    result = {"generated": datetime.now().isoformat(timespec="seconds"),
              "selection": sel,
              "test_days": int(t.size), "contenders": list(aligned),
              "depths": config.DEPTHS.tolist(), "argo_counts": counts, "argo": table}
    head = label(sel["headline"], sel)
    result["gap_closed"] = gap_closed(table)
    result["hazard"] = hazard_block(meta)
    result["heatwave"] = heatwave_block(meta)
    result["cyclones"] = cyclone_block(aligned, t, head)
    try:
        result["incois"] = incois_block(aligned, t, meta)
    except Exception as e:  # the Argo block stands on its own; the failure is reported
        result["incois_error"] = f"{type(e).__name__}: {e}"
    from . import embed
    cands = [r for r, v in sel["runs"].items() if v["role"] == "candidate"]
    result["embedding_screen"] = embed.screen(cands)
    inspect_runs = [r for r in dict.fromkeys([sel["headline"], result["embedding_screen"]["chosen"]])
                    if r and list((config.OUTPUT / "embedding").glob(f"{r}_*.nc"))]
    result["embedding"] = {r: embed.inspect(r) for r in inspect_runs}
    JSON.write_text(json.dumps(result, indent=1))
    PROFILES.write_text(json.dumps(meta))
    DOCS.write_text(report(result), encoding="utf-8")
    print(f"eval done in {time.time() - t0:.0f} s: {counts['casts_used']} casts")
    return result


def demo() -> None:
    z = np.array([4.0, 12.0, 20.0, 60.0, 400.0, 1010.0])
    v = np.array([29.0, 28.0, 27.0, 20.0, 10.0, 6.0])
    ok = np.array([True, True, False, True, True, True])
    p = profile_on_depths(z, v, ok)
    assert p[0] == 29.0, "shallowest good level within 5.5 m is the surface value"
    assert np.isclose(p[1], 29.0 - 1 / 8), "5 m interpolated between 4 and 12 m"
    assert np.isnan(p[3]), "20 m: the level there failed QC, and 12 -> 60 m is a 48 m gap"
    assert np.isnan(p[11]), "300 m: 60 -> 400 m is wider than 0.2 x 300"
    assert np.isnan(p[14]), "1000 m: 400 -> 1010 m is wider than 0.2 x 1000"
    p3 = profile_on_depths(np.array([900.0, 1050.0]), np.array([8.0, 6.5]), np.ones(2, bool))
    assert np.isclose(p3[14], 8.0 - 1.5 * 100 / 150), "1000 m inside a 150 m gap is interpolated"
    assert np.isnan(profile_on_depths(z, v, np.zeros(6, bool))).all()
    p2 = profile_on_depths(np.array([8.0, 30.0]), np.array([28.0, 26.0]), np.ones(2, bool))
    assert np.isnan(p2[0]) and np.isnan(p2[1]), "never extrapolated above the first good level"
    s = scores(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 4.0]), None)
    assert np.isclose(s["bias"], -1 / 3) and np.isclose(s["rmse"], np.sqrt(1 / 3))
    lin = np.array([30.0, 29.5, 29.0, 28.0, 27.0, 25.0, 22.0, 20.0, 18.0, 16.0, 14.0, 12.0, 10.0, 8.0, 6.0])
    assert np.isclose(isotherm_depth(lin, 26.0), 40.0) and np.isclose(isotherm_depth(lin, 20.0), 100.0)
    area = (0.5 * (4 + 3.5) * 5 + 0.5 * (3.5 + 3) * 5 + 0.5 * (3 + 2) * 10 + 0.5 * (2 + 1) * 10
            + 0.5 * 1 * 10)
    assert np.isclose(tchp(lin), config.RHO_REF * config.CP0 * area / 1e7), "trapezoid to the 26 degC crossing"
    assert tchp(lin - 5) == 0.0, "surface below 26 degC: no heat potential"
    assert np.isnan(tchp(np.full(15, 29.0))), "never cools to 26 degC: unknown, not a bound"
    gap = np.array(lin); gap[2] = np.nan
    assert np.isnan(tchp(gap)) and np.isnan(isotherm_depth(gap, 26.0)), "a gap above the crossing"
    step = np.full(15, 28.0); step[4:] = 20.0          # 28 degC to 20 m, 20 degC from 30 m
    assert np.isclose(mld(step), 20.0 + 0.2 / 8.0 * 10), "0.2 degC from the 10 m value"
    assert np.isnan(mld(np.full(15, 28.0))), "never departs: unknown, not 1000 m"
    t = {"x": {"climatology": [{"rmse": 1.0}], "GLORYS (ceiling)": [{"rmse": 0.5}], "m": [{"rmse": 0.75}]}}
    import unittest.mock as um
    with um.patch.object(config, "DEPTHS", np.array([0.0])):
        assert gap_closed(t)["x"]["m"] == [0.5]
    print("evaluate ok: profile rules (QC, gaps, no extrapolation), metrics, isotherms, TCHP, MLD, gap closed")


if __name__ == "__main__":
    import sys
    demo() if "--demo" in sys.argv else run()
