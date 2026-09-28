"""The eval harness. The only thing that writes numbers anyone may quote.

    python -m oceanembed.evaluate

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
    return sorted(p.parent.name for p in config.RUNS.glob("*/best.pt"))


ROLE_NOTE = {
    "candidate": "a candidate for the model",
    "ablation": "ablation: an input removed, to measure what it adds",
    "comparison": "extended-window comparison: trained from 1993, where salinity before "
                  "~2010 is not satellite salinity; never shown as the model",
}


def selection() -> dict:
    """The headline model, chosen on the validation block only (hard rule 6), before any
    test number is computed: the candidate with the lowest best validation loss. All
    candidates share the train block, so their normalised losses are comparable."""
    from .train import load_config

    runs = {}
    for run in model_runs():
        cfg = load_config(config.RUNS / run / "config.toml")
        hist = json.loads((config.RUNS / run / "history.json").read_text())
        best = min(hist, key=lambda h: h["val_loss"])
        runs[run] = {"role": cfg.get("role", "candidate"), "arch": cfg["arch"],
                     "lags": cfg["lags"], "inputs": cfg["inputs"], "epochs_run": len(hist),
                     "best_epoch": best["epoch"], "val_loss": best["val_loss"],
                     "val_rmse_per_depth": best["val_rmse_per_depth"]}
    candidates = {k: v for k, v in runs.items() if v["role"] == "candidate"}
    headline = min(candidates, key=lambda k: candidates[k]["val_loss"]) if candidates else None
    return {"rule": "lowest best validation loss among candidates (validation block only)",
            "headline": headline, "runs": runs}


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


def incois_block(aligned: dict, t: np.ndarray) -> dict:
    """Compare everyone with INCOIS's gridded Argo at its own 1 deg / 10-day grid."""
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
    st = grid.Stencil((1.0,) * 4, 4, "4 x 4 block mean to 1 deg")
    table = {}
    obs_all, pred_all, where_all = [], {k: [] for k in aligned}, []
    for s, ts in enumerate(ds["time"].values.astype("datetime64[D]")):
        win = (t >= ts - 5) & (t < ts + 5)
        if win.sum() < 8:
            continue
        for z in shared:
            k = int(np.flatnonzero(np.isclose(config.DEPTHS, z))[0])
            temp = ds["TEMP"].isel(time=s).sel(ZAX=z).values
            sal = ds["SAL"].isel(time=s).sel(ZAX=z).values
            p = gsw.p_from_z(-z, lat[:, None])
            sa = gsw.SA_from_SP(sal, p, lon[None, :], lat[:, None])
            pt = gsw.pt0_from_t(sa, temp, p)
            coarse = {}
            for name, v in aligned.items():
                m, share = grid.regrid(np.nanmean(v[win, k], axis=0), st, lat.size, lon.size)
                m[share < config.OCEAN_FRACTION_MIN] = np.nan
                coarse[name] = m
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
    return {"table": table, "notes": notes, "shared_depths": shared, "file": path.name}


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


def report(result: dict) -> str:
    c = result["argo_counts"]
    lines = [
        "# Eval results — generated, never hand-edited",
        "",
        f"Generated by `python -m oceanembed.evaluate` on {result['generated']}. "
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
        "| Run | Role | Encoder | Lags (days) | Inputs | Best epoch | Val loss | Val RMSE 0 / 100 / 300 / 1000 m (°C) |",
        "|---|---|---|---|---|---:|---:|---|",
        *[f"| {k} | {ROLE_NOTE.get(v['role'], v['role'])} | {v['arch']} | {v['lags']} | "
          f"{', '.join(v['inputs'])} | {v['best_epoch']}/{v['epochs_run']} | {v['val_loss']:.4f} | "
          + " / ".join(f"{v['val_rmse_per_depth'][i]:.3f}" for i in (0, 7, 11, 14)) + " |"
          for k, v in result["selection"]["runs"].items()],
        "",
        "## Argo casts (test block)",
        "",
        "| Count | Value |", "|---|---:|",
        *[f"| {k.replace('_', ' ')} | {v} |" for k, v in c.items()],
        "",
        *_tables(result["argo"], "Argo"),
    ]
    if "incois" in result:
        inc = result["incois"]
        lines += ["## INCOIS gridded Argo (`incois_argo_10d_VAM`, 1° / 10-day)", "",
                  *[f"- {n}" for n in inc["notes"]], "", *_tables(inc["table"], "INCOIS")]
    for run, e in result.get("embedding", {}).items():
        lines += [f"## Embedding inspection · {run}", ""]
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
                      "The encoder is given the day of year, so the same measures on the day "
                      "of year alone are the bar the embedding has to clear:", "",
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
    try:
        result["incois"] = incois_block(aligned, t)
    except Exception as e:  # the Argo block stands on its own; the failure is reported
        result["incois_error"] = f"{type(e).__name__}: {e}"
    from . import embed
    result["embedding"] = {r: embed.inspect(r) for r in model_runs()
                           if list((config.OUTPUT / "embedding").glob(f"{r}_*.nc"))}
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
    print("evaluate ok: profile rules (QC, gaps, no extrapolation), metrics")


if __name__ == "__main__":
    import sys
    demo() if "--demo" in sys.argv else run()
