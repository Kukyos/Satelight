"""What the embedding captures, measured (docs/03-limitations.md L10).

Called by the harness; its numbers land in docs/13-eval-results.md.

1. **Seasons, never taught.** The daily embedding (one vector per day) is clustered with
   k-means into 4 groups, and the groups are compared with the four Indian Ocean monsoon
   seasons (Dec-Feb winter monsoon, Mar-May spring inter-monsoon, Jun-Sep summer
   monsoon, Oct-Nov autumn inter-monsoon) by normalised mutual information. And for each
   test day, is its nearest neighbour in embedding space (excluding +/-3 days of itself)
   in the same season? Chance is reported beside it.
2. **Mixed-layer depth, never taught.** GLORYS `mlotst` is not an input and not a
   target. A linear probe is fitted from the per-cell embedding to it on the validation
   block and scored on the test block, beside the same probe fitted on the raw eight
   satellite channels at the cell. If the embedding's R^2 is higher, it holds something
   about the upper ocean that the pixel alone does not.
   Which run's embedding is inspected for this is chosen before any test number, on the
   validation block alone (`screen`): the same probe fitted on its first year and scored
   on the rest (D-09).
3. **Pictures.** The first three principal components of the per-cell embedding, as RGB,
   for a few test days: data/figures/embedding_<run>_<day>.png.
"""

from __future__ import annotations

import numpy as np

from . import config, data

SEASON_NAMES = ["Winter monsoon (DJF)", "Spring inter-monsoon (MAM)",
                "Summer monsoon (JJAS)", "Autumn inter-monsoon (ON)"]
SAMPLE_CELLS = 1500
MLD_SOURCE = "mld"


def season(t: np.ndarray) -> np.ndarray:
    m = (t.astype("datetime64[M]").astype(int) % 12) + 1
    return np.select([np.isin(m, [12, 1, 2]), np.isin(m, [3, 4, 5]),
                      np.isin(m, [6, 7, 8, 9])], [0, 1, 2], 3)


def season_scores(daily: np.ndarray, t: np.ndarray, seed: int = 0) -> dict:
    """The embedding's scores, beside the same scores for the day of year alone. The
    encoder is given sin/cos of the day of year as an input, so the embedding only shows
    something about the ocean if it beats that control."""
    out = _season_scores(daily, t, seed)
    out["day_of_year_control"] = _season_scores(data.doy_fields(t), t, seed)
    return out


def _season_scores(daily: np.ndarray, t: np.ndarray, seed: int) -> dict:
    from sklearn.cluster import KMeans
    from sklearn.metrics import normalized_mutual_info_score

    s = season(t)
    z = (daily - daily.mean(0)) / (daily.std(0) + 1e-6)
    labels = KMeans(4, n_init=10, random_state=seed).fit_predict(z)
    d = ((z[:, None] - z[None]) ** 2).sum(-1)
    gap = np.abs(np.arange(len(t))[:, None] - np.arange(len(t))[None])
    d[gap <= 3] = np.inf
    nn = d.argmin(1)
    same = float((s[nn] == s).mean())
    chance = float(sum((np.mean(s == k)) ** 2 for k in range(4)))
    rng = np.random.default_rng(seed)
    shuffled = float(normalized_mutual_info_score(rng.permutation(s), labels))
    return {"days": int(len(t)), "kmeans_k": 4,
            "nmi_clusters_vs_season": float(normalized_mutual_info_score(s, labels)),
            "nmi_shuffled_seasons": shuffled,
            "nearest_neighbour_same_season": same,
            "nearest_neighbour_chance": chance}


def _sample(cell, x, mld, clim, sea, seed):
    """Rows of (embedding, raw features, MLD, MLD climatology) from random sea cells on
    every day. The raw features are what the encoder itself was given at that cell: the
    eight satellite channels, latitude, longitude, sea-floor depth and day of year."""
    rng = np.random.default_rng(seed)
    js, is_ = np.nonzero(sea)
    st = data.static_fields()
    E, X, Y, C = [], [], [], []
    for d in range(cell.shape[0]):
        k = rng.choice(js.size, SAMPLE_CELLS, replace=False)
        j, i = js[k], is_[k]
        y = mld[d, j, i]
        raw = np.column_stack([x[d][:, j, i].T, st["lat"][j, i], st["lon"][j, i],
                               st["bathy"][j, i],
                               np.broadcast_to(clim["doy"][d], (j.size, 2))])
        ok = np.isfinite(y) & np.isfinite(raw).all(1)
        E.append(cell[d][:, j, i].T[ok])
        X.append(raw[ok])
        Y.append(y[ok])
        C.append(clim["mld"][clim["month"][d], j, i][ok])
    return (np.concatenate(E).astype(np.float32), np.concatenate(X), np.concatenate(Y),
            np.concatenate(C))


def mld_probe(run: str) -> dict:
    """Linear probe for mixed-layer depth: fit on val, score on test.

    Scored twice: R^2 on MLD itself, and R^2 on MLD anomalies from a per-cell monthly
    climatology (fitted on the val block), so that neither probe can win on the season
    alone."""
    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score

    from .predict import predict_span

    sea = data.sea_mask()
    va, vb = config.SPLITS["val"]
    mld_val, t_val = data._read(MLD_SOURCE, "mld", va, vb)
    month = lambda tt: tt.astype("datetime64[M]").astype(int) % 12  # noqa: E731
    clim_mld = np.stack([np.nanmean(mld_val[month(t_val) == m], axis=0) for m in range(12)])
    rows = {}
    for split in ("val", "test"):
        a, b = config.SPLITS[split]
        _, t, (cell, _) = predict_span(run, a, b, with_embedding=True)
        x, _, tx = data.load_raw(split, config.INPUTS, with_target=False)
        mld, tm = data._read(MLD_SOURCE, "mld", a, b)
        common = np.intersect1d(np.intersect1d(t, tx), tm)
        pick = lambda arr, tt: arr[np.searchsorted(tt, common)]  # noqa: E731
        clim = {"mld": clim_mld, "month": month(common), "doy": data.doy_fields(common)}
        rows[split] = _sample(pick(cell, t), pick(x, tx), pick(mld, tm), clim, sea, seed=1)
        del cell, x, mld
    (Ev, Xv, Yv, Cv), (Et, Xt, Yt, Ct) = rows["val"], rows["test"]
    mu, sd = Xv.mean(0), Xv.std(0) + 1e-6
    out = {"fit_on": "val block", "scored_on": "test block",
           "rows_fit": int(Yv.size), "rows_scored": int(Yt.size),
           "label": "GLORYS mlotst (mixed-layer depth, m): never an input, never a target"}
    for name, (fv, ft) in {"embedding (32 per cell)": (Ev, Et),
                           "raw features the encoder saw (13 per cell)": ((Xv - mu) / sd,
                                                                          (Xt - mu) / sd)
                           }.items():
        m = Ridge(alpha=1.0).fit(fv, Yv)
        p = m.predict(ft)
        out[name] = {"r2_test": float(r2_score(Yt, p)),
                     "r2_test_anomaly": float(r2_score(Yt - Ct, p - Ct))}
    return out


SCREEN_SPLIT = np.datetime64("2022-01-01")   # val block: probe fitted before, scored after


def screen(runs: list[str]) -> dict:
    """The MLD probe on the validation block only: fitted on 2021, scored on 2022, for each
    run's embedding and for the raw features. Picks the run that carries S4 without the
    test block (hard rule 6). Cached per run in runs/<run>/probe_val.json."""
    import json

    from sklearn.linear_model import Ridge
    from sklearn.metrics import r2_score

    from .predict import predict_span

    out, todo = {}, []
    for r in runs:
        f = config.RUNS / r / "probe_val.json"
        if f.exists():
            out[r] = json.loads(f.read_text())
        else:
            todo.append(r)
    if todo:
        a, b = config.SPLITS["val"]
        sea = data.sea_mask()
        x, _, tx = data.load_raw("val", config.INPUTS, with_target=False)
        mld, tm = data._read(MLD_SOURCE, "mld", a, b)
        month = lambda tt: tt.astype("datetime64[M]").astype(int) % 12  # noqa: E731
        for r in todo:
            _, t, (cell, _) = predict_span(r, a, b, with_embedding=True)
            common = np.intersect1d(np.intersect1d(t, tx), tm)
            pick = lambda arr, tt: arr[np.searchsorted(tt, common)]  # noqa: E731
            m = pick(mld, tm)
            fit = common < SCREEN_SPLIT
            clim = np.stack([np.nanmean(m[fit & (month(common) == k)], axis=0) for k in range(12)])
            rows = {}
            for part, k in (("fit", fit), ("score", ~fit)):
                c = {"mld": clim, "month": month(common[k]), "doy": data.doy_fields(common[k])}
                rows[part] = _sample(pick(cell, t)[k], pick(x, tx)[k], m[k], c, sea, seed=1)
            del cell
            (Ef, Xf, Yf, _), (Es, Xs, Ys, _) = rows["fit"], rows["score"]
            mu, sd = Xf.mean(0), Xf.std(0) + 1e-6
            res = {"fit": "val block before 2022", "scored": "val block 2022"}
            for name, (fa, fb) in {"embedding": (Ef, Es),
                                   "raw": ((Xf - mu) / sd, (Xs - mu) / sd)}.items():
                res[f"r2_{name}"] = float(r2_score(Ys, Ridge(alpha=1.0).fit(fa, Yf).predict(fb)))
            (config.RUNS / r / "probe_val.json").write_text(json.dumps(res, indent=1))
            out[r] = res
    best = max(out, key=lambda r: out[r]["r2_embedding"] - out[r]["r2_raw"]) if out else None
    return {"rule": "candidate whose embedding beats the raw features on the val-block "
                    "MLD probe by the widest margin (fit 2021, scored 2022)",
            "chosen": best, "runs": out}


def pictures(run: str, days: list[str]) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import xarray as xr

    from .predict import EMB_DIR

    sea = data.sea_mask()
    fig_dir = config.DATA / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for day in days:
        path = EMB_DIR / f"{run}_{day[:4]}.nc"
        if not path.exists():
            continue
        with xr.open_dataset(path) as ds:
            e = ds["cell"].sel(time=day).values.astype(np.float32)   # (D, H, W)
        v = e[:, sea].T
        v = v - v.mean(0)
        _, _, vt = np.linalg.svd(v, full_matrices=False)
        pc = v @ vt[:3].T
        lo, hi = np.percentile(pc, [2, 98], axis=0)
        rgb = np.clip((pc - lo) / (hi - lo), 0, 1)
        img = np.ones((config.NLAT, config.NLON, 3)) * 0.08
        img[sea] = rgb
        plt.figure(figsize=(9.6, 4.4), dpi=150)
        plt.imshow(img, origin="lower", extent=[45, 105, 5, 30])
        plt.title(f"Satelight per-cell embedding, first 3 principal components as RGB — {day}")
        plt.xlabel("longitude (°E)")
        plt.ylabel("latitude (°N)")
        out = fig_dir / f"embedding_{run}_{day}.png"
        plt.savefig(out, bbox_inches="tight", facecolor="white")
        plt.close()
        written.append(out.name)
    return written


def inspect(run: str) -> dict:
    import xarray as xr

    from .predict import EMB_DIR

    files = sorted(EMB_DIR.glob(f"{run}_*.nc"))
    out = {"run": run}
    if files:
        with xr.open_mfdataset(files) as ds:
            daily = ds["daily"].values
            t = ds["time"].values.astype("datetime64[D]")
        out["seasons"] = season_scores(daily, t)
        out["figures"] = pictures(run, ["2023-01-15", "2023-07-15", "2024-05-01", "2024-10-15"])
    try:
        out["mld_probe"] = mld_probe(run)
    except FileNotFoundError as e:
        out["mld_probe_error"] = f"MLD not fetched: {e}"
    out["verdict"] = verdict(out)
    return out


def verdict(out: dict) -> dict:
    """The two S4 proofs as amended 2026-09-28 (docs/02-requirements.md)."""
    v = {}
    if "seasons" in out:
        s = out["seasons"]
        v["clusters by season better than the day of year alone (NMI)"] = (
            s["nmi_clusters_vs_season"] > s["day_of_year_control"]["nmi_clusters_vs_season"])
    if "mld_probe" in out:
        m = [x for x in out["mld_probe"].values() if isinstance(x, dict)]
        v["MLD probe on the embedding beats the raw features (R² on test)"] = (
            m[0]["r2_test"] > m[1]["r2_test"])
    return v


def demo() -> None:
    t = np.array(["2023-01-05", "2023-04-01", "2023-07-01", "2023-10-20", "2023-12-31"],
                 dtype="datetime64[D]")
    assert season(t).tolist() == [0, 1, 2, 3, 0]
    rng = np.random.default_rng(0)
    tt = config.days(config.SPLITS["test"][0], config.SPLITS["test"][1])
    s = season(tt)
    daily = rng.normal(size=(tt.size, 8)) + 4 * np.eye(4, 8)[s]
    r = season_scores(daily, tt)
    assert r["nmi_clusters_vs_season"] > 0.8 > r["nmi_shuffled_seasons"], r
    v = verdict({"seasons": r, "mld_probe": {"label": "x", "emb": {"r2_test": 0.2},
                                             "raw": {"r2_test": 0.3}}})
    assert list(v.values()) == [r["nmi_clusters_vs_season"] > r["day_of_year_control"]
                                ["nmi_clusters_vs_season"], False], v
    print("embed ok: seasons recovered from a planted signal, shuffled control near zero")


if __name__ == "__main__":
    demo()
